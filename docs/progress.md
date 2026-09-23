# Progress

Current milestone status, what has actually been verified, unresolved
issues, and concrete next steps. See `docs/architecture.md` for accepted
architecture/decisions and `docs/matching-spec.md` for approved
matching/classification behavior — this file tracks state, not design.

---

## Current milestone

**Milestone 3 (web UI) is complete and pushed.** All three milestones
(ingestion, matching, web UI) are implemented, tested, and verified against
the real stack, most recently on 2026-09-22. No milestone is in progress.

---

## Milestone 1 — Ingestion

Fetches dated Tel Aviv-Yafo building snapshots from OSM via the ohsome API,
validates/normalizes them, persists to MinIO + Postgres metadata.

**Verified end-to-end (2026-08-20):**

1. `docker compose up` works, after building a local `Dockerfile` extending
   `apache/airflow:3.3.1` with this project's business-logic dependencies
   (geopandas/shapely/pyproj/requests/psycopg) — `_PIP_ADDITIONAL_REQUIREMENTS`
   was deliberately avoided per Airflow's own docs ("ONLY for quick checks").
2. `POST /elements/geometry` confirmed blocked (HTTP 403) from two
   independent real networks. Workaround (querying
   `/elementsFullHistory/geometry` with a 1-second range and filtering by
   `@validFrom`) cross-checked against `/elements/count` — counts matched
   exactly.
3. ohsome's `properties=tags` response shape confirmed to match what
   `normalize_feature()` assumed.
4. AOI clipping confirmed: `bpolys` clips geometry, not just filters by
   intersection — checked every feature not fully `.contains()`-ed by the AOI
   polygon; residual area was 1e-11–1e-14 deg² (floating-point noise, not
   real overhang).

Real run results (feature count / invalid-then-repaired count):

| requested_time | feature_count | invalid_geometry_count |
|---|---|---|
| 2025-07-01 | 27,013 | 3 |
| 2026-06-01 | 26,996 | 4 |
| 2026-07-01 | 26,982 | 4 |

Idempotency verified: re-triggering with the same `requested_times` left the
`snapshots` table at 3 rows.

**`source_query_version` v2 (2026-09-16):** `make_valid` could return a
`GeometryCollection` for 3 of 26,982 features. `validate.py` now extracts
only polygonal parts (`make_valid+extract_polygons`); re-running produced
identical feature counts and a 0.000000 m² total area delta. v1 rows are
retained (versioning, not overwriting), per CLAUDE.md.

**Snapshot range:** expanded to 7 snapshots — annually from 2021-07-01
through 2025-07-01, plus 2026-06-01 and 2026-07-01 — to support the 1-month /
1-year / 5-year intervals the web UI offers. Checked before trusting the
5-year span: OSM building count in the AOI was already 96.7% of today's
count back in 2021 (26,088 → 26,982, net +894 / +3.4% over 5 years), so the
long-interval comparison reflects real change, not mapping-completeness
growth:

| date | buildings | Δ vs prev |
|---|---|---|
| 2021-07-01 | 26,088 | — |
| 2022-07-01 | 26,149 | +61 |
| 2023-07-01 | 26,731 | +582 |
| 2024-07-01 | 27,030 | +299 |
| 2025-07-01 | 27,013 | −17 |
| 2026-06-01 | 26,996 | −17 |
| 2026-07-01 | 26,982 | −14 |

---

## Milestone 2 — Matching & classification

Behavior was specified before implementation (`docs/matching-spec.md`).

**Verified end-to-end (2026-09-16)** against the real v2 snapshots:

| pair | unchanged | modified_geometry | modified_attributes | modified_geometry_and_attributes | added | removed | ambiguous |
|---|---|---|---|---|---|---|---|
| monthly (2026-06→2026-07) | 26,944 | 30 | 4 | 0 | 4 | 18 | 0 |
| yearly (2025-07→2026-07) | 26,628 | 145 | 130 | 5 | 72 | 103 | 2 |

Both pairs satisfy the consistency equations in `docs/matching-spec.md` §7
exactly. Spot-checked individually, not just by count:

- Both `ambiguous` records are exactly the two cross-ID overlaps predicted
  from real-data analysis: `way/488475407`~`relation/19933969`
  (iou=0.0636), `way/506832165`~`way/1427652677` (iou=0.2230).
- The re-traced block's `way/149268397` classified `modified_geometry` with
  iou=0.1193, iou_centroid_aligned=0.6904, centroid_shift_m=9.72,
  area_ratio=0.69 — matching the spec's predictions to four decimal places.

Idempotency verified: re-triggering left the `changesets` table at 2 rows.

---

## Milestone 3 — Web UI

React + TypeScript + MapLibre + MUI viewer over PostGIS vector tiles.

**Verified on the live stack (2026-09-22):**

- 186,989 `snapshot_features` rows (7 snapshots) and 11,274 `change_features`
  rows (7 changesets) published, with exact per-changeset parity against the
  `changesets` metadata table for all 7 intervals.
- Measured change-row share, confirming the "store only non-unchanged"
  design in `docs/architecture.md` §5 (this is what answers the "does this
  grow quadratically" concern — see below):

  | interval | `unchanged` | actually changed | % changed |
  |---|---|---|---|
  | 2026-06-01 → 2026-07-01 | 26,944 | 56 | 0.21% |
  | 2025-07-01 → 2026-07-01 | 26,628 | 457 | 1.69% |
  | 2021-07-01 → 2026-07-01 | 21,825 | 5,430 | 19.9% |

- The yearly changeset's z12 Tel Aviv tile decodes to 423 real features with
  the expected classification mix; the 5-year tile to 4,308.
- `way/149268397` round-trips its spec values through the API (iou 0.1193,
  iou_centroid_aligned 0.6904, centroid_shift_m 9.72) with both before and
  after geometry present, and appears in all 7 snapshots in its history.
- The UI boots with no console errors, MapLibre initializes with WebGL, the
  basemap style/sprites load, and the filter panel shows counts matching
  Milestone 2's monthly table exactly (Added 4, Removed 18, Geometry changed
  30, Attributes changed 4, Ambiguous 0).
- Full suite green: 118 offline Python tests, 41 db tests, 22 frontend tests
  (181 total), ruff clean, `tsc --noEmit` clean, production build succeeds.

**Map canvas rendered black — found and fixed (2026-09-22).** The earlier
claim in this file that headless Chrome cannot render the map (because
MapLibre selects tiles inside its `requestAnimationFrame` loop) was wrong and
masked a real bug: the user saw a solid black map area in a real browser,
with DOM overlay controls (nav buttons, scale bar, attribution) working
normally. Root cause, confirmed via Chrome DevTools Protocol (`Network.
enable` + polling pending requests, then `window.__map` introspection):
Vite's dependency optimizer pre-bundles `maplibre-gl` but does not correctly
rewrite the import inside the module Worker MapLibre spawns for tile/
protobuf parsing, so `node_modules/.vite/deps/maplibre-gl-worker.mjs` 404s
and that request hangs forever. The worker never responds, no tile ever
finishes decoding, `map.isStyleLoaded()` stays `false` indefinitely, and
nothing is ever painted -- with no console error, because the failure is a
silently-stuck fetch, not a thrown exception. `get.webgl.org` rendering fine
in the same browser ruled out a GPU/driver problem before this was found.

Fixed in `web/vite.config.ts` by adding `optimizeDeps: { exclude:
["maplibre-gl"] }`, which makes Vite serve the package unbundled so the
worker's internal import resolves. Verified visually after the fix (headless
screenshot, `Emulation.setDeviceMetricsOverride` + `Page.captureScreenshot`
after a real wait): full Tel Aviv-Yafo basemap renders -- coastline, road
network, and neighbourhood labels all visible. This also means headless
verification of the map canvas is possible after all (new headless Chrome
does run the render loop); the "not verifiable headlessly" claim in earlier
drafts of this file should not be trusted for future map-rendering checks.

A second, unrelated bug was found investigating this: clicking the map
before the `changes-fill` layer exists (e.g. immediately after switching
interval, before the new layer is added) threw
`queryRenderedFeatures ... does not exist in the map's style` instead of a
no-op. Fixed in `web/src/components/MapView.tsx`'s click handler with an
`instance.getLayer(...)` guard.

Still worth confirming in your own browser: `make web`, then
http://localhost:5173. Click `way/149268397` in the 1-year interval to
confirm the before/after overlay and the "moved ~9.7 m" explanation render
as intended.

**Default-selected interval showed no map highlights on page load -- found
and fixed (2026-09-22).** Reported by the user: the changeset selected by
default on load (whichever the API returns first, e.g. the 1-month interval)
never showed its coloured change layer on the map, and reselecting the same
interval did nothing (an unchanged React state value is a no-op, as
expected) -- only switching to a *different* interval and back made it
appear. Root cause was `MapView.tsx` gating `addSource`/`addLayer` calls on
`map.isStyleLoaded()`. Per MapLibre's own source
(`Style#loaded()`), that method requires every current source's *tiles* to
have finished downloading, not just the style spec being parsed -- so at
the moment `changesetId` first becomes non-null (typically while the base
map's own vector tiles for the current view are still in flight),
`isStyleLoaded()` is false, a `styledata` listener gets registered to retry,
but the specific event transition where `isStyleLoaded()` finally flips true
does not reliably fire as a *new* `styledata` event for a late listener --
so the listener's callback simply never ran again, silently, with no
exception. Fixed by switching to MapLibre's `style.load` event (fires once
the style spec/sources/layers are structurally parsed, independent of tile
downloads) tracked via a `styleReady` state flag, rather than polling
`isStyleLoaded()`. Verified via Chrome DevTools Protocol on a fresh page
load with no interaction: the `changes-fill`/`changes-outline` layers and
their tile source now exist immediately.

**Hovering a wide timeline bracket blocked clicking the row below --
found and fixed (2026-09-22).** Reported by the user: hovering "5 years" (a
full-width bracket) prevented comfortably clicking the "1 year" brackets
underneath. Cause: MUI `Tooltip`'s default "bottom" placement pops the
tooltip bubble directly over the row beneath the hovered element, which for
a full-width bracket covers the entire next row. Fixed by removing
per-bracket tooltips entirely in favour of a persistent caption below the
whole track, driven by hover-or-selection state -- informative without ever
sitting on top of anything clickable. Verified via CDP: dispatching a
hover on "5 years" and then checking `document.elementFromPoint` at each
"1 year" button's centre confirms every one of them is still its own
top-level hit target.

A test suite regression surfaced alongside the first fix and was fixed
too: `App.test.tsx`'s "loads change detail" test called the map's
`onSelectChange` callback without first waiting for the `listChangesets()`
fetch to actually settle -- racing against the effect that clears `change`
whenever `selectedChangesetId` changes. It had been passing by lucky
timing; unrelated render-count changes elsewhere tipped the race until it
failed consistently. Fixed by waiting for `mapProps.at(-1)?.changesetId` to
reach its expected value before firing the selection, in both tests that
do this.

---

## Refactor pass (2026-09-23)

A review-driven cleanup across `src/matching`, `src/db`, `src/publish`,
`dags/`, `api/` and `web/src`, constrained to be behavior-preserving. Net
−178 lines. Two real defects surfaced while verifying it; both are described
below because the verification, not the refactor, is the interesting part.

**What changed.**

- `src/matching/crs.py` is new: `to_metric` / `to_crs84` replace the three
  separate `Transformer.from_crs` pairs that `features.py`, `pipeline.py` and
  `render.py` each built, and carry the repair-after-reprojection rule that
  only `features.py` previously applied.
- `CLASSIFICATIONS` is now `get_args(Classification)` in `changeset.py`
  instead of a hand-restated tuple in `pipeline.py`.
- `compute_metrics` binds each geometry's area and centroid once; Shapely
  recomputes on every property access and each was read three times.
- Candidate generation passes `predicate="intersects"` to `STRtree.query`, so
  non-touching bbox hits are discarded in C before the overlay runs.
- `_connected_components` is a BFS over an adjacency dict rather than a
  hand-rolled union-find with path halving.
- `src/db/_upsert.py` holds the insert-then-read-back sequence both metadata
  modules duplicated; each keeps its own SQL and row type.
- `src/publish/postgis.py` shares one `_load_via_staging` helper between the
  two publish functions, with row building split into generators.
- `dags/common.py` holds the connection names, instant parsing, natural-key
  builder, `current_params()`, and the single snapshot/comparison inventory.
- `api/queries.py` composes `LIST_CHANGESETS` and `GET_CHANGESET` from one
  base string instead of deriving one from the other by `.replace()`.
- `web/src/format.ts` holds `isoDate` / `shortLabel` / `fmt`, previously
  redefined in three components. `MapView.tsx` went from 298 lines and six
  effects to 46 lines over four hooks in `web/src/components/map/`, and both
  `as never` casts are gone (the code now typechecks properly).

**Found: change-layer output was not reproducible.** Verifying the refactor
against the stored MinIO artifacts showed differences in ambiguous records.
Root cause predates this work: `pair_metrics` was built by iterating
frozensets of osm_ids, that insertion order became the `candidates` array
order of the exported GeoJSON, and Python randomizes string hashing per
process. Demonstrated directly — the same changeset built twice under
`PYTHONHASHSEED=1` and `=2` produced byte-different GeoJSON. This violated
CLAUDE.md's "make deterministic output ordering part of exported artifacts
and tests". Fixed by iterating `sorted(a_ids)` / `sorted(b_ids)`; after the
fix the same changeset under `PYTHONHASHSEED=1` and `=999` is byte-identical.
Regression test: `test_pair_metrics_ordering_is_deterministic_not_hash_dependent`,
which passes under four different hash seeds.

**Rejected: an IoU optimization that looked exact and was not.** Replacing
`geom_a.union(geom_b).area` with `|A| + |B| - |A and B|` avoids the union
overlay and benchmarked 1.7x faster. Measured against the real snapshots it
is *not* equivalent: it disagreed on 5,164 of 26,978 ID-matched pairs by up
to 2.1e-12, and returned `iou > 1.0` for 5,178 pairs, because the two area
computations round differently. Far below every threshold in `config.py`, but
it changes stored metric values, which per CLAUDE.md means a new
`ALGORITHM_VERSION` rather than a silent rewrite. Reverted; the reasoning is
recorded in `metrics._iou` and pinned by `test_iou_never_exceeds_one`.

**Found: stale DAG defaults.** `ingest_osm_building_snapshots` still
defaulted to 3 requested times while 7 snapshots were ingested and published
and `publish_to_postgis` listed all 7 — so triggering ingestion on its
defaults covered under half the dataset. Both now read `REQUESTED_TIMES` from
`dags/common.py`. The two tests that pinned the stale values were rewritten
to assert against the shared inventory (they were the only existing tests
that needed changing).

**Verification performed (2026-09-23).**

1. `ruff check .` clean; `pytest` 126 passed, and `pytest -m db` 41 passed
   against the real local Postgres.
2. `airflow dags list-import-errors` in the running stack: no errors, so
   `from dags.common import ...` resolves in the container as well as under
   pytest.
3. Output equality against the real data: the refactored pipeline was re-run
   on all 7 stored changesets (~188k change records) and compared field by
   field with the change layers in MinIO. **No value differences anywhere** —
   every classification, metric, osm_id, reason and flag identical. Two
   changesets were byte-identical; the other five differed only in the
   `candidates` array ordering of 70 ambiguous records total (5/35/17/11/2),
   which is the determinism fix above.
4. Web: `tsc --noEmit` clean (both former `as never` casts removed, so the
   map's style expression and overlay data are now genuinely type-checked),
   27 vitest tests pass, and `npm run build` succeeds.
5. Browser, via CDP against headless Chrome on the running stack: map canvas
   mounts, all 8 intervals render, clicking an interval changes the selection
   ("5 years ... 5,430 changes" -> "1 year ... 712 changes"), the
   classification filter toggles, the basemap swaps (positron -> dark) with
   the map surviving the `setStyle`, and no console errors or uncaught
   exceptions.

**Found and fixed: satellite basemap showed no data (2026-09-23).** Reported
by the user after the refactor: switching to satellite view left the map with
no buildings or changes on it at all, and switching interval did not help.
Two distinct faults, the first exposed by the refactor and the second latent
in the original:

1. *`style.load` never fired for the satellite style.* MapLibre's `setStyle`
   defaults to `diff: true`. Given the satellite style — an inline object
   rather than a URL — the diff succeeds and strips this project's sources
   and layers (they are not part of the new style spec) **without** a full
   reload, so `style.load` never fires, `styleReady` never returns to true,
   and the layers are never rebuilt. The street styles are URLs, so they
   always fully reload and always fired it, which is why only satellite broke.
   Fixed with `setStyle(style, { diff: false })`. Confirmed by instrumenting
   the page: before the fix, satellite gave `styleLoadFired=false` and zero
   of our layers; after, all five layers and the `changes` source are present
   in satellite, across interval switches, and back on street.

   The pre-refactor code survived this by accident: its single build effect
   listed `basemap` in its dependencies, so it re-ran in the same commit as
   the `setStyle` call while `styleReady` was still a stale `true`, re-adding
   the layers moments after the diff removed them. Extracting the effect into
   `useChangeLayers` dropped that dependency and exposed the real flaw.

2. *Readiness was React state, so it could be read stale.* Toggling the
   theme while in satellite then threw `Style is not done loading` from
   `addSource`. The layer hooks run later in the same commit as the style
   swap, and `mode` is one of their dependencies, so they re-ran with the
   readiness value captured at render time — still `true` — and touched a
   style that was mid-reload. This hazard existed in the original too; it was
   simply never reached. Fixed by making readiness a ref
   (`StyleState.ready`), which is accurate synchronously, with a companion
   `version` counter as the state that triggers the rebuild render.

Regression tests in `web/src/components/__tests__/useMapInstance.test.tsx`
cover both: that `setStyle` is called with `{ diff: false }`, and that the
readiness ref is already `false` by the time `setStyle` is invoked. Each was
confirmed to fail when its fix is reverted. Verified end to end in a real
browser via CDP: street renders, satellite requests Esri imagery and keeps
the map, interval switching and theme toggling both survive while in
satellite, returning to street works, and no uncaught exceptions throughout.

**Caveat on the headless harness.** Headless Chrome here never requests
`/tiles/changes/` or `/tiles/buildings/` at all - MapLibre mounts and loads
the basemap, but the overlay sources never fetch. This was confirmed to be a
property of the headless environment rather than the refactor by stashing the
web changes and re-running: the pre-refactor `MapView` requests zero change
tiles in the same harness. So the vector-tile path itself is unverified here
and is worth a look in a real browser (`make up`, `make web`,
http://localhost:5173): confirm the coloured change layer draws, switching
interval swaps it, unchecking a class removes it from the map, and clicking a
highlighted building opens the detail panel with the before/after outlines.

---

## Concrete next steps

None committed to yet — no milestone is currently in progress. Candidates
raised but deliberately deferred (see `docs/architecture.md` §8 for why):
retrofit Airflow Assets across the ingest→match→publish chain; systematic
block-shift detection; arbitrary on-demand interval computation.
