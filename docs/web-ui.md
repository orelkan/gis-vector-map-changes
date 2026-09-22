# Web UI: architecture and data model

Status: **implemented and verified against the live stack (2026-09-22).**

A React + TypeScript viewer for the ingested snapshots and computed
changesets, with a MapLibre GL map driven by vector tiles generated in
PostGIS.

---

## 1. Where the data lives

```
Airflow (milestones 1-2)         milestone 3
ingest ──▶ match ──▶ MinIO ──▶ publish_to_postgis ──▶ PostGIS ──▶ FastAPI ──▶ React
                    GeoJSON       (Airflow DAG)       + GIST      MVT+JSON   +MapLibre
```

MinIO remains the **immutable store of record**. PostGIS is a *derived
serving layer* — rebuildable at any time by re-running
`publish_to_postgis`, and never written to by the API, which is read-only.

---

## 2. "Before" and "after" are per-interval, not absolute

A **changeset compares exactly two snapshots**, A (earlier) and B (later).
So before/after are always *relative to the selected interval*. The same
building has different before/after in different intervals:
`way/149268397` compared over the 1-month interval has its 2026-06 geometry
as "before", but over the 1-year interval has its 2025-07 geometry.

Because that alone cannot answer "what about many different timestamps",
the detail panel has two parts:

1. **Interval view** — the selected changeset's before/after, overlaid on the
   map (before dashed, after solid), with classification, reason, match
   method/score and all five metrics.
2. **Timeline view** — the building across *every* snapshot held, with the
   changesets it appears as a change in. Served by
   `GET /api/history/{osm_id}`, backed by a dedicated
   `snapshot_features(osm_id)` index (the composite `(snapshot_id, osm_id)`
   key cannot serve a query filtered on `osm_id` alone).

---

## 3. Why this does not grow quadratically

With N snapshots there are N(N−1)/2 possible pairs, so materializing every
change record per pair would be quadratic — at ~27k features each, 21 pairs
would be ~567k rows of mostly-nothing. Two things prevent that.

**(1) Feature geometry is stored once per snapshot — linear.**
`snapshot_features` holds each building once per snapshot and is shared by
every comparison involving it; it is never duplicated per changeset. Adding a
snapshot costs ~27k rows regardless of how many intervals you then examine.

**(2) A changeset stores only what actually changed.** Measured on the real
data:

| interval | `unchanged` | actually changed | % changed |
|---|---|---|---|
| 2026-06-01 → 2026-07-01 | 26,944 | 56 | 0.21% |
| 2025-07-01 → 2026-07-01 | 26,628 | 457 | 1.69% |
| 2021-07-01 → 2026-07-01 | 21,825 | 5,430 | 19.9% |

98–99.8% of a fully-materialized changeset would be `unchanged` rows
carrying no information, so **`change_features` never stores `unchanged`**.
It is derived instead: a building present in both snapshots with no
`change_features` row is unchanged. A
`CHECK (classification <> 'unchanged')` constraint enforces this in the
database, so a loader bug cannot quietly reintroduce the rows. Summary
counts come from the `changesets` metadata table, which already has them.

**Measured result:** 11,274 change rows across all 7 published changesets,
against 186,989 snapshot-feature rows. Materializing all 21 possible pairs
would still land in the low tens of thousands.

---

## 4. How this shapes the map

Two layers, with very different costs:

- **Context layer** (grey, ~27k buildings) — `snapshot_features` for the
  interval's *after* snapshot. One shared source, reused by every interval.
  `minzoom` 15 plus `ST_SimplifyPreserveTopology` by zoom, because a
  city-wide tile would otherwise carry every building.
- **Change layer** (coloured, tens to a few thousand) — `change_features`
  for the selected changeset. Small enough to render at every zoom with no
  special handling, which is why the city-wide view shows changes only.

Clicking a change queries the rendered tile (`queryRenderedFeatures`) and
then fetches `/api/changes/{id}` for the full record and before/after
geometry.

---

## 5. Schema notes

- **`geom_3857` is a materialized column, not a functional index.** The
  obvious `CREATE INDEX ... USING GIST (ST_Transform(geom, 3857))` is
  impossible: `ST_Transform` is `STABLE`, not `IMMUTABLE`, so PostgreSQL
  rejects it in an index expression. Storing the projected geometry also
  avoids reprojecting 27k geometries per tile request.
- **Everything is `ST_Multi`-normalized to MultiPolygon**, because a typed
  geometry column must pick one type and snapshots legitimately contain
  both. This is only clean because the earlier v1→v2 ingestion fix
  eliminated `GeometryCollection`.
- **Before/after geometry is derived inside the INSERT**, by joining to
  already-published `snapshot_features`, rather than by a follow-up UPDATE:
  the `added_has_b` / `removed_has_a` CHECK constraints are evaluated per
  row at insert time and PostgreSQL cannot defer CHECK constraints. This is
  also why `publish_changeset` is structurally downstream of
  `publish_snapshot`.

---

## 6. Interface choices

- **MapLibre GL JS** (BSD-3): native MVT, GPU rendering, and data-driven
  styling — colouring by classification is one `match` expression rather
  than per-feature JavaScript. Mapbox GL JS v2+ is proprietary with billable
  map loads; Leaflet's vector-tile plugin is effectively stagnant and lacks
  layer-level restyling.
- **One FastAPI service** for both tiles and JSON, since a detail API is
  needed regardless; a dedicated tile server would mean two services for no
  gain at this data scale.
- **Intervals are picked from computed changesets**, not arbitrary date
  ranges — that keeps `algorithm_version` provenance intact and matches the
  pipeline's versioned-result model. A new interval means running
  `build_changesets` for that pair.
- **Basemap follows the theme**: OpenFreeMap `positron` (light) /`dark`,
  both muted so classification colours dominate.

---

## 7. Attribution (required)

Building data © OpenStreetMap contributors, ODbL. Basemap © OpenFreeMap
(© OpenMapTiles). Both are displayed persistently in the UI; the API also
returns attribution on `/api/health` and in an `X-Attribution` header.

---

## 8. Verification

Run `make up`, `make migrate`, then the three DAGs
(`ingest_osm_building_snapshots` → `build_changesets` → `publish_to_postgis`),
then `make web`.

Confirmed on the live stack:
- 186,989 snapshot features and 11,274 change features published, with
  per-changeset parity against the `changesets` metadata table exact for
  all 7 intervals.
- The yearly changeset's z12 Tel Aviv tile decodes to 423 real features with
  the expected classification mix; the 5-year tile to 4,308.
- `way/149268397` round-trips its spec values through the API
  (iou 0.1193, iou_centroid_aligned 0.6904, centroid_shift_m 9.72) with both
  before and after geometry present, and appears in all 7 snapshots in its
  history.
- The UI boots with no console errors, MapLibre initialises with WebGL, the
  basemap style/sprites load, and the filter panel shows counts matching
  `docs/matching-behavior.md` §7 exactly (Added 4, Removed 18, Geometry
  changed 30, Attributes changed 4, Ambiguous 0 for the 1-month interval).

**Not verifiable headlessly:** MapLibre selects tiles during its
`requestAnimationFrame` render loop, which headless Chrome does not run — a
screenshot shows the map canvas unpainted (a single flat colour) and no tile
requests, even though the style, sprites and attribution all load and the
tile endpoints are independently verified by decoding their output. The map
visual therefore needs a real browser.
