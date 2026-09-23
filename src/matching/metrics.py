"""Similarity metrics between two loaded features, computed in METRIC_CRS.

Every metric's interpretation is documented in docs/matching-spec.md
section 3, including why iou_centroid_aligned is recorded but deliberately
NOT used as a classification gate (validated against real re-traced
buildings: it separates "positional" from "shape" disagreement, but does
not cleanly binary-separate "repositioned" from "reshaped").
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity
from shapely.geometry.base import BaseGeometry

from src.matching.config import SIGNIFICANT_TAGS
from src.matching.features import LoadedFeature


@dataclass(frozen=True)
class MatchMetrics:
    iou: float
    iou_centroid_aligned: float
    centroid_shift_m: float
    area_ratio: float
    hausdorff_m: float
    attrs_changed: tuple[str, ...]  # subset of SIGNIFICANT_TAGS that differ


def _iou(geom_a: BaseGeometry, geom_b: BaseGeometry) -> float:
    """Intersection-over-union, via the union overlay.

    The union area looks arithmetically recoverable as |A| + |B| - |A and B|,
    which would skip the (expensive) overlay. Measured against the real
    ingested snapshots, that shortcut is NOT equivalent: it disagreed with
    this form on 5,164 of 26,978 ID-matched pairs by up to 2.1e-12, and
    produced iou > 1.0 for 5,178 pairs, because the two area computations
    round differently. The differences are far below every threshold in
    config.py, but they change stored metric values -- which per CLAUDE.md
    means a new ALGORITHM_VERSION, not a silent rewrite. Keeping the overlay.
    """
    union_area = geom_a.union(geom_b).area
    if union_area == 0:
        return 0.0
    return geom_a.intersection(geom_b).area / union_area


def compute_metrics(a: LoadedFeature, b: LoadedFeature) -> MatchMetrics:
    """Compute all documented metrics between two already-reprojected
    features. Order matters for area_ratio (area_b / area_a) and
    centroid_shift (a's centroid to b's) -- callers pass (old, new).
    """
    ga, gb = a.geometry, b.geometry
    # Shapely recomputes these on every property access, and each is used
    # more than once below.
    area_a, area_b = ga.area, gb.area
    centroid_a, centroid_b = ga.centroid, gb.centroid

    iou = _iou(ga, gb)

    gb_aligned = affinity.translate(
        gb, xoff=centroid_a.x - centroid_b.x, yoff=centroid_a.y - centroid_b.y
    )
    iou_centroid_aligned = _iou(ga, gb_aligned)

    return MatchMetrics(
        iou=iou,
        iou_centroid_aligned=iou_centroid_aligned,
        centroid_shift_m=centroid_a.distance(centroid_b),
        area_ratio=(area_b / area_a) if area_a else 0.0,
        hausdorff_m=ga.hausdorff_distance(gb),
        attrs_changed=tuple(
            tag for tag in SIGNIFICANT_TAGS if a.attrs.get(tag) != b.attrs.get(tag)
        ),
    )
