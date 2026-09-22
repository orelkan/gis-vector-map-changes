# Architecture and significant decisions

Accepted architecture for GIS Vector Map Changes and the rationale behind
decisions that would otherwise only exist in conversation history. See
`docs/matching-spec.md` for matching/classification behavior and
`docs/progress.md` for current status and verification results.

---

## 1. System overview

```
Airflow (ingest)     Airflow (match)      Airflow (publish)
     |                     |                     |
     v                     v                     v
  MinIO (GeoJSON) ----> src/matching ----> PostGIS (snapshot_features,
  + Postgres              |                       change_features)
  (snapshots,              v                       |
   changesets              MinIO (change layers)   v
   metadata)                                   FastAPI (api/)
                                                     |
                                                     v
                                              React + MapLibre (web/)
```

- **MinIO** is the immutable store of record for every snapshot and
  changeset's full GeoJSON. Nothing overwrites it; a new algorithm version or
  re-ingestion creates a new object, never replaces one in place.
- **Postgres (non-PostGIS-feature tables)** holds `snapshots` and
  `changesets` metadata: identifiers, provenance, object-store URIs, summary
  counts. Small, queried directly, never through Airflow Variables (per
  CLAUDE.md).
- **PostGIS feature tables** (`snapshot_features`, `change_features`) are a
  *derived serving layer* — rebuildable at any time by re-running
  `publish_to_postgis` against MinIO, and never written to by the API, which
  is read-only. See §5.
- **DAG files stay orchestration-only.** All business logic (normalization,
  matching, classification, publishing) lives in `src/`, importable and
  testable without Airflow, per CLAUDE.md's architecture rules.

---

## 2. Data source: OSM/ohsome, not Overture Maps

**Decision:** build the MVP on OpenStreetMap building data via the ohsome
API, not Overture Maps.

**Why:** the project needs two genuinely dated historical snapshots of the
same area. Overture Maps' public release retention is short (on the order of
60 days at the time this was investigated) — old releases are not kept
publicly accessible, which breaks the "two dated snapshots" requirement
outright. OSM's full edit history goes back to the project's start, and
HeiGIT's ohsome API serves point-in-time extracts from that history, which is
exactly what a multi-year comparison (§3 in `docs/matching-spec.md`, the
2021→2026 span) needs.

**Trade-off accepted:** OSM data quality varies by how well an area is
mapped, and "change" can reflect mapping-completeness improving over time
rather than real-world construction. This was checked, not assumed — Tel
Aviv-Yafo was already 96.7% as densely mapped in 2021 as in 2026 (see
`docs/progress.md`), so a 5-year comparison is not dominated by mapping
noise for this AOI. Revisit this check before trusting a longer span or a
different AOI.

**ohsome endpoint note:** `POST /elements/geometry` returns HTTP 403
(confirmed from two independent networks — not a sandbox artifact); no
public explanation was found. `src/ingestion/ohsome_client.py` instead uses
`POST /elementsFullHistory/geometry` with a minimal (1-second) time range at
the target instant, then filters the response to `@validFrom == <requested
instant>` in `src/ingestion/snapshot.py`. Cross-checked against
`/elements/count` for the same instant/bbox — counts matched exactly.

---

## 3. Immutability, versioning, and idempotency

- Snapshots and changesets are identified by natural keys (source,
  `source_query_version`, layer, `aoi_id`, `aoi_version`, requested time /
  snapshot pair + `algorithm_version`), enforced with database uniqueness
  constraints, not just application checks.
- A changed extraction or matching definition creates a **new version**
  rather than rewriting history — e.g. `source_query_version` went v1→v2 when
  geometry repair changed (§4), and both versions' rows remain queryable.
- Re-running ingestion, matching, or publishing with the same inputs and
  version is a no-op on row counts (verified in `docs/progress.md`), never a
  duplicate insert.
- Where atomic replacement is needed (publishing a changeset), it happens as
  delete-then-insert scoped to one `snapshot_id`/`changeset_id` inside a
  single transaction.

---

## 4. Geometry validation and CRS conventions

- All metric geometry computation (area, distance, IoU, Hausdorff) happens in
  **EPSG:2039** (Israel 1993 / Israeli TM Grid, metres), verified to cover the
  AOI. Never EPSG:4326 for metric work, per CLAUDE.md.
- Snapshots are stored in **OGC:CRS84**; reprojection happens at load. Tile
  serving additionally stores a **materialized EPSG:3857** column (§5) since
  `ST_Transform` is `STABLE`, not `IMMUTABLE`, and cannot be used in a GIST
  index expression — the projected geometry has to be stored, not indexed
  functionally.
- Invalid input geometry is repaired with `make_valid`, never silently
  discarded; both the original validity and the repair method are recorded
  (`repair_method`, `original_valid`). A repair that produces a
  `GeometryCollection` (found in 3 of 26,982 real features) is reduced to its
  polygonal parts (`make_valid+extract_polygons`, `source_query_version` v2)
  so the "snapshots contain only Polygon/MultiPolygon" invariant holds for
  matching and for the typed PostGIS geometry columns.
- All feature geometry is normalized to **MultiPolygon** at the PostGIS layer
  (via `ST_Multi`), because a typed column must pick one type and real
  snapshots legitimately contain both — clean only because the v1→v2 fix
  above already eliminated `GeometryCollection`.

---

## 5. PostGIS serving layer

`sql/003_create_feature_tables.sql`:

- **`snapshot_features`** — one row per building per snapshot; shared,
  linear growth (not duplicated per comparison). Unique on
  `(snapshot_id, osm_id)`; a separate btree index on `osm_id` alone serves
  the cross-snapshot timeline lookup, since the composite key can't. GIST
  index on the materialized `geom_3857` column.
- **`change_features`** — only non-`unchanged` records
  (`added`/`removed`/`modified_*`/`ambiguous`), enforced by
  `CHECK (classification <> 'unchanged')`. "Unchanged" is derived, never
  stored: a building present in both snapshots with no `change_features` row
  for that changeset is unchanged. This choice, and the row-count math behind
  it, is explained in `docs/progress.md` §"quadratic-growth concern".
  `geom_a`/`geom_b` (before/after, 4326) are derived **inside the INSERT** by
  joining to already-published `snapshot_features`, not by a follow-up
  UPDATE — PostgreSQL cannot defer CHECK constraints
  (`added_has_b`/`removed_has_a`), so an insert-then-update sequence would
  fail the check at insert time. This is also why `publish_to_postgis`
  structurally runs `publish_snapshot` before `publish_changeset`.
- Both tables keep 4326 (authoritative source CRS, needed for GeoJSON output)
  alongside the materialized 3857 (tile rendering), rather than converting
  losslessly back and forth per request.

---

## 6. Before/after semantics and the quadratic-growth concern

A changeset compares exactly two snapshots, A (earlier) and B (later), so
"before"/"after" are always *relative to the selected interval*, never
absolute — the same building has a different "before" depending on which
interval is selected (`way/149268397` over the 1-month interval has its
2026-06 geometry as before; over the 1-year interval, its 2025-07 geometry).
Because a single before/after pair can't answer "what happened across many
different timestamps," the UI's detail panel has two views:

1. **Interval view** — the selected changeset's before/after overlaid on the
   map (before dashed, after solid), with classification, reason, match
   method/score, and all five metrics from `docs/matching-spec.md` §3.
2. **Timeline view** — the building across *every* snapshot held, plus which
   changesets it appears as a change in. Served by
   `GET /api/features/{osm_id}/history`, backed by the dedicated
   `snapshot_features(osm_id)` index from §5 (the composite
   `(snapshot_id, osm_id)` key can't serve a query filtered on `osm_id`
   alone).

**Why per-interval storage does not grow quadratically.** With N snapshots
there are N(N−1)/2 possible pairs, so materializing a full change record per
pair looks quadratic — at ~27k features each, 21 pairs would be ~567k rows
of mostly nothing. Two things prevent that: (1) `snapshot_features` stores
each building once per snapshot, shared by every comparison that touches
it — linear in the number of snapshots, never duplicated per pair; (2)
`change_features` stores only actual changes (§5), and real changes are a
small fraction of all features (98–99.8% `unchanged` at 1-month/1-year
spacing — see `docs/progress.md` for the measured table). The two layers
this produces have very different costs on the map: a shared grey context
layer (`snapshot_features` for the interval's "after" snapshot, one source
reused by every interval, `minzoom`-gated plus
`ST_SimplifyPreserveTopology`) and a small coloured change layer
(`change_features` for the selected changeset, cheap enough to render at
every zoom).

---

## 7. API and frontend

- **One FastAPI service** (`api/`) serves both MVT tiles (`ST_AsMVT`) and the
  JSON detail/history endpoints, rather than a dedicated tile server — a
  detail API is needed regardless, and at this data scale a second service
  buys nothing. Read-only; no writes to PostGIS from the API.
- **MapLibre GL JS** (BSD-3-Clause, no key/billing) over Mapbox GL JS
  (proprietary, billable map loads) or Leaflet's vector-tile plugin
  (effectively stagnant, lacks layer-level restyling). Native MVT support and
  data-driven styling make "colour by classification" one style expression.
- **Basemap: OpenFreeMap**, theme-paired (`positron` light / `dark`), both
  muted so classification colours dominate; attribution for OSM data (ODbL)
  and the basemap is always visible, per CLAUDE.md.
- **React + TypeScript + MUI v9**, light/dark modes with the basemap swapped
  to match — a dark UI under a bright basemap reads as broken.
- **Intervals are picked from computed changesets**, never an arbitrary
  date range picked in the UI — this keeps `algorithm_version` provenance
  intact and matches the pipeline's versioned-result model. A new interval
  means running `build_changesets` for that pair first.
- Tile classification filters are a validated allow-list, never
  string-interpolated into SQL.
- **The interval picker is a timeline in presentation only** (`ChangesetTimeline`):
  ticks mark the snapshot dates that exist, and each computed changeset draws
  as a clickable bracket between its two dates, grouped into rows by
  `span_label` (longest span on top) so nested intervals -- the 5-year span
  containing five 1-year steps, which contain the trailing 1-month step --
  read as zoom levels. There is deliberately no drag-an-endpoint affordance:
  that would imply arbitrary on-demand interval computation, which is out of
  scope (§8) for the same provenance reason the picker itself is.
- **Optional satellite basemap**: Esri World Imagery (raster, no API key or
  billing account), toggled independently of the light/dark UI theme via a
  floating control on the map, since satellite imagery has no meaningful
  "dark mode" of its own. Chosen over Mapbox/Maxar/Bing satellite layers,
  which all require a key -- the same "no key/billing" bar the OpenFreeMap
  vector basemap was already held to. Its attribution is picked up
  automatically by MapLibre's own `AttributionControl` once it's the active
  source, since the raster source declares an `attribution` string; no
  separate attribution wiring was needed.

---

## 8. Deliberately deferred (not lacking, chosen)

- **Airflow Assets** for the ingest→match→publish chain: a real fit
  ("changeset ready" is exactly an Asset), and a stated learning goal, but
  retrofitting all three DAGs was judged bigger than the milestone that
  raised it. Do this as its own small milestone rather than folding it in
  silently.
- **Systematic block-shift detection** (recognising a whole neighbourhood
  moved together as one survey realignment, rather than reporting each
  building's shift independently): needs spatial clustering of shift
  vectors; real data has exercised the need for this (one re-traced block,
  see `docs/matching-spec.md` §1) but the feature itself is unbuilt.
- **Arbitrary on-demand interval computation**, **Kubernetes / Celery /
  Spark / Kafka / dbt / production deployment / ML-based matching /
  road-network processing** — excluded per CLAUDE.md's scope-control list
  unless explicitly requested.
