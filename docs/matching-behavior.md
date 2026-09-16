# Matching & classification: defined behavior

Status: **implemented and verified against the real ingested snapshots
(2026-09-16).** See §7 for the acceptance results.

CLAUDE.md requires that expected behavior be defined *before* matching is
built:

> Before implementing matching, define expected behavior for: stable IDs with
> changed geometry; different IDs with nearly identical geometry; one old
> building split into several new buildings; several old buildings merged into
> one; small coordinate shifts; geometry repairs that alter comparison
> metrics; features clipped by the AOI boundary.

This document is that definition. Every threshold here is derived from
measurement of the actual ingested snapshots (2025-07-01, 2026-06-01,
2026-07-01), computed in EPSG:2039, not chosen by intuition. The measurements
are reproduced in §1 so the reasoning can be re-checked when the data changes.

---

## 1. Empirical baseline

| | monthly (2026-06-01→07-01) | yearly (2025-07-01→2026-07-01) |
|---|---|---|
| features A → B | 26,996 → 26,982 | 27,013 → 26,982 |
| osm_id persists | 26,978 (99.93%) | 26,908 (99.61%) |
| id disappeared | 18 | 105 |
| id appeared | 4 | 74 |
| geometry differs (same id) | 32 | 164 |
| significant attrs differ | 4 | 135 |

Findings that drive the design:

1. **OSM IDs are extremely stable here** (99.6–99.9%), so ID is genuinely
   strong evidence — matching should exploit it rather than doing 27k×27k
   spatial work.
2. **The dominant "geometry change" is not real-world change.** 18 of the 32
   monthly changes are one block (`way/1492680xx`–`1492684xx`) systematically
   re-traced 7.6–14.1 m to the southwest (bearings 186–223°). Their IoU is
   0.119–0.32 — naive IoU thresholding would call these "completely different
   buildings." They are the same buildings, re-surveyed.
3. **Minimum IoU for any same-id pair was 0.119** — no persisting ID ever
   became a disjoint geometry. (Justifies §4 Stage 1.)
4. **Real split/merge cases: none.** 103 clean removals, 72 clean additions,
   and exactly 2 cross-ID partial overlaps in the yearly pair. Split/merge
   logic therefore cannot be validated against real data and must be covered
   by hand-authored fixtures.
5. **`raw_tags` churn (207 yearly) far exceeds significant-tag churn (129)**,
   confirming that `modified_attributes` must key off a documented subset
   rather than "any tag changed."

---

## 2. Scope of a comparison

A change set compares exactly two snapshots. Both must share `aoi_id`,
`aoi_version`, `layer`, and `source_query_version`; the pipeline refuses to run
otherwise. This is what makes AOI-boundary features safe to compare (§6g):
identical clipping on both sides is deterministic.

All metric computation happens in **EPSG:2039** (Israel 1993 / Israeli TM Grid,
metres), verified to cover the AOI. Snapshots are stored in OGC:CRS84;
reprojection happens at load. Per CLAUDE.md, metric work never happens in
EPSG:4326.

---

## 3. Metrics

Computed for every candidate pair; stored on every matched/ambiguous record.

| metric | definition | interpretation |
|---|---|---|
| `iou` | `inter.area / union.area` | Overall agreement. Position-sensitive: a pure translation destroys it. |
| `iou_centroid_aligned` | IoU after translating B so centroids coincide | **Shape** agreement independent of position. A large gap vs `iou` means the discrepancy is positional, not a reshape. |
| `centroid_shift_m` | distance between centroids | How far it moved. |
| `area_ratio` | `area_B / area_A` | Growth/shrink; 1.0 = size preserved. |
| `hausdorff_m` | Hausdorff distance | Worst-case boundary deviation; catches a single badly-moved vertex that IoU dilutes. |
| `attrs_changed` | list of differing significant tags | Which of `building`/`category`/`name` differ. |

**On `iou_centroid_aligned`:** validated against the re-traced block — it lifts
those pairs from IoU 0.12 to 0.65–1.00, correctly showing most of the
disagreement is positional. It does **not** cleanly binary-separate
"repositioned" from "reshaped", because that block was genuinely re-traced:
moved *and* redrawn (area ratios 0.66–0.92). It is therefore recorded as an
explanatory metric that describes a change compositionally, and is deliberately
**not** used as a classification gate.

---

## 4. Matching algorithm

**Stage 1 — ID matching.** Features sharing an `osm_id` are matched:
`match_method="osm_id"`, `match_score=1.0`. An ID match wins outright;
geometry is measured but does not veto it (justified by finding #3). Handles
~99.9% of features.

**Stage 2 — spatial candidates, for the remainder only** (the ~18–105
disappeared and ~4–74 appeared). STRtree over the appeared set; candidates are
pairs with **intersection area > 0**.

> **Boundary semantics (explicit, per CLAUDE.md):** candidacy requires positive
> *overlapping area*, **not** the `intersects` predicate. This matters
> concretely — Tel Aviv terraced housing shares walls, so `intersects` would
> generate many spurious candidates from mere edge contact. Touching-only is
> not a candidate.

**Stage 3 — score** each candidate using §3.

**Stage 4 — resolve:**

| situation | outcome |
|---|---|
| no candidate for an A-feature | `removed` |
| no candidate for a B-feature | `added` |
| 1:1 and `iou ≥ T_CROSS_ID_MATCH` | matched, `match_method="geometry"` |
| 1:1 and `0 < iou < T_CROSS_ID_MATCH` | `ambiguous` (`partial_overlap`) |
| one A ↔ many B | `ambiguous` (`split_candidate`) |
| many A ↔ one B | `ambiguous` (`merge_candidate`) |

Ambiguous records retain **all** candidate pairs and scores. Per CLAUDE.md the
highest score is never silently chosen to force a resolution.

**Stage 5 — classify each matched pair:**

```
geometry_changed   = iou < T_UNCHANGED_IOU
attributes_changed = any significant tag differs

both        -> modified_geometry_and_attributes
geometry    -> modified_geometry
attributes  -> modified_attributes
neither     -> unchanged
```

---

## 5. Thresholds

| name | value | justification from real data |
|---|---|---|
| `T_UNCHANGED_IOU` | 0.99 | Coordinate-identical pairs give IoU 1.0. Two monthly pairs differ textually but are effectively identical (IoU 0.9999/1.0000, 0.00 m shift) — vertex reordering/precision, correctly absorbed as `unchanged`. The next real value down is 0.9255 (a genuine 0.48 m edit). Any value in 0.93–0.999 works; 0.99 is the round, defensible choice. |
| `T_CROSS_ID_MATCH` | 0.50 | Deliberately strict for *different*-ID pairs. The only two real cross-ID overlaps score 0.064 and 0.223, so both land in `ambiguous` — the honest outcome (§6b). Nothing in the real data auto-matches across IDs. |
| `SIGNIFICANT_TAGS` | `building`, `category`, `name` | Yearly `raw_tags` churn is 207 vs 129 for these; the subset filters real noise (`addr:*`, `source`, survey metadata). |
| `METRIC_CRS` | `EPSG:2039` | Israel 1993 / Israeli TM Grid, metres; verified to cover the AOI. |

These live in one documented config module with unit tests, per CLAUDE.md
("treat numerical tolerances as named, documented configuration with tests").

---

## 6. Required edge-case behavior

**(a) Stable ID, changed geometry** → matched on ID, classified
`modified_geometry`; all metrics recorded so the *nature* of the change stays
explainable. *Real:* 32 monthly / 164 yearly, including the re-traced block,
which lands here with low `iou` but high `iou_centroid_aligned` — the metric
pair tells the story without a special case.

**(b) Different IDs, near-identical geometry** → Stage 2; auto-matched only at
`iou ≥ 0.50`, otherwise `ambiguous`. *Real:* both yearly cases are correctly
ambiguous. `way/506832165 → way/1427652677` has 93% of the *old* building
inside the new one but IoU 0.223 (new is ~4× larger) — a redevelopment, not a
1:1 rename. `way/488475407 → relation/19933969` is a way→relation conversion at
IoU 0.064. Forcing either into `unchanged` would be wrong; both deserve review.

**(c) Split (one old → several new)** → `ambiguous`, reason `split_candidate`,
all parts retained with per-part coverage. *Not present in real data —
fixture-only.*

**(d) Merge (several old → one new)** → `ambiguous`, reason `merge_candidate`,
symmetric to (c). *Not present in real data — fixture-only.*

**(e) Small coordinate shifts** → absorbed as `unchanged` when `iou ≥ 0.99`.
*Real:* two monthly features (IoU 0.9999/1.0000, 0.00 m) correctly absorbed —
genuinely distinct from the re-traced block (7.6–14.1 m), which is not absorbed
and is correctly reported as `modified_geometry`.

**(f) Geometry repairs altering metrics** → metrics are computed on the
repaired/normalized geometry (the original is preserved alongside by
ingestion). Any change record where either side had `repair_method` set carries
`involves_repaired_geometry=true`, so a suspicious metric can be traced to a
repair rather than a real edit. *Real:* the 3 features repaired in both
snapshots are stable across them (repaired-vs-repaired IoU = 1.0000), so
repairs are deterministic and do not by themselves manufacture changes.

**(g) Features clipped by the AOI boundary** → safe *because* §2 forbids
comparing across differing `aoi_version`; identical clipping means a clipped
building is clipped identically on both sides. *Real:* 21 features lie within
0.5 m of the AOI edge, stable across snapshots. Their change records carry
`touches_aoi_boundary=true` so a partial footprint is never mistaken for a
shrinking building. Comparing different `aoi_version`s is a hard error.

---

## 7. Expected outputs (acceptance test for the implementation)

**Status: implemented and run against the real snapshots (2026-09-16).**
Every number below is what the real `build_changesets` DAG actually
produced, cross-checked against the predictions made while writing this
spec -- both changesets' counts satisfy the consistency equations exactly,
and every spot-checked `osm_id` (the re-traced block, both ambiguous pairs)
matches its predicted IoU to four decimal places. See
[README.md](../README.md) for the run details.

**Monthly (2026-06-01 → 2026-07-01)** — exact, matches the pre-implementation
prediction with zero discrepancy:

| class | count |
|---|---|
| `unchanged` | 26,944 |
| `modified_geometry` | 30 |
| `modified_attributes` | 4 |
| `modified_geometry_and_attributes` | 0 |
| `added` | 4 |
| `removed` | 18 |
| `ambiguous` | 0 |

Consistency: 26,944+30+4+0 = 26,978 ID-matched; +18 removed = 26,996 (A);
+4 added = 26,982 (B).

**Yearly (2025-07-01 → 2026-07-01)** — exact:

| class | count |
|---|---|
| `unchanged` | 26,628 |
| `modified_geometry` | 145 |
| `modified_attributes` | 130 |
| `modified_geometry_and_attributes` | 5 |
| `added` | 72 |
| `removed` | 103 |
| `ambiguous` | 2 |

Consistency: 26,628+145+130+5 = 26,908 ID-matched (matches §1's measured
26,908 exactly); +103 removed +2 ambiguous (both 1:1 `partial_overlap`
pairs, one A-id each) = 27,013 (A); +72 added +2 ambiguous = 26,982 (B). The
pre-implementation estimate in an earlier draft of this section
("`modified_attributes` ≈129") undercounted by one tag-changed feature that
also had its geometry change -- 130 + 5 = 135 total attrs-changed, which
does match §1's raw baseline measurement exactly. The unchanged/
modified_geometry split (≈26,629/≈145 estimated) landed at 26,628/145,
within the margin the estimate flagged as undetermined.

Both ambiguous records are exactly the two pairs identified in §1's
real-data analysis: `way/488475407` ~ `relation/19933969` (iou=0.0636) and
`way/506832165` ~ `way/1427652677` (iou=0.2230). `way/149268397` (the
re-traced block) is `modified_geometry` with iou=0.1193,
iou_centroid_aligned=0.6904, centroid_shift_m=9.72, area_ratio=0.69 --
matching the prediction in §1 exactly.

Per CLAUDE.md ("avoid tests that assert only row counts"), the test suite
also asserts specific `osm_id`s and their classifications, not just these
totals -- see tests/matching/.

---

## 8. Out of scope

- **Systematic block-shift detection** (recognising a whole neighbourhood
  moved together as one survey realignment) — needs spatial clustering of
  shift vectors; its own milestone if wanted.
- **Loading features into queryable PostGIS tables** — only needed when
  matching actually runs; that schema belongs with the implementation.
- Road networks, vector tiles, web map, canonical cross-source identities.

---

## 9. Verification plan

1. Hand-authored fixtures covering CLAUDE.md's full required list — critically
   split, merge, and ambiguous cases, which **real data cannot exercise**
   (finding #4).
2. Unit tests per metric against known geometries (known IoU/area/centroid).
3. Threshold tests asserting behavior exactly at `T_UNCHANGED_IOU` and
   `T_CROSS_ID_MATCH` boundaries.
4. Failure tests: mismatched CRS and mismatched `aoi_version` both raise
   rather than silently proceeding.
5. End-to-end against the real snapshots, asserting §7's table.
6. Determinism: identical inputs produce byte-identical ordered output.
