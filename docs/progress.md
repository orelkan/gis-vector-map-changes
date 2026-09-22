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

## Concrete next steps

None committed to yet — no milestone is currently in progress. Candidates
raised but deliberately deferred (see `docs/architecture.md` §8 for why):
retrofit Airflow Assets across the ingest→match→publish chain; systematic
block-shift detection; arbitrary on-demand interval computation.
