"""Named, documented configuration for the matching pipeline.

Every value here is justified in docs/matching-spec.md against
measurement of the real ingested Tel Aviv-Yafo snapshots -- none of these
are intuition-picked. Bump ALGORITHM_VERSION whenever any value here, or
the matching logic itself, changes: per CLAUDE.md's versioning rules, a new
matching algorithm or threshold configuration creates a new versioned
result rather than silently rewriting history.
"""

from __future__ import annotations

ALGORITHM_VERSION = "v1"

# Reproject snapshots (stored as OGC:CRS84) into this CRS before computing
# any metric. Never compute area/distance in EPSG:4326 -- CLAUDE.md's
# geospatial correctness rules. Verified to cover the Tel Aviv-Yafo AOI;
# see docs/matching-spec.md section 2.
METRIC_CRS = "EPSG:2039"

# Stage 5: an ID- or geometry-matched pair with iou >= this is `unchanged`
# geometry-wise; below it, `modified_geometry`. See docs/matching-spec.md
# section 5 -- justified by the real-data IoU distribution (coordinate-
# identical pairs give 1.0; the lowest genuinely-unchanged pair was 0.9999;
# the next real value down was 0.9255, a genuine 0.48m edit).
T_UNCHANGED_IOU = 0.99

# Stage 4: a 1:1 spatial candidate pair (different osm_ids) is only
# auto-matched at iou >= this; below it, the pair is `ambiguous` rather than
# silently matched. Deliberately strict -- see docs/matching-spec.md
# section 5 (the only two real cross-id overlaps score 0.064 and 0.223, both
# correctly land in `ambiguous`).
T_CROSS_ID_MATCH = 0.50

# modified_attributes only looks at these tags, not "any tag changed" --
# raw_tags churn far exceeds churn in this subset in the real data (207 vs
# 129 yearly). See docs/matching-spec.md section 1, finding 5.
SIGNIFICANT_TAGS = ("building", "category", "name")

# A change record involving a feature within this distance of the AOI
# boundary is flagged touches_aoi_boundary=True, so a partial footprint is
# never mistaken for a shrinking building. Real AOI-boundary features in
# the ingested data sit within a fraction of this distance of the edge; see
# docs/matching-spec.md section 6g.
AOI_BOUNDARY_DISTANCE_M = 0.5
