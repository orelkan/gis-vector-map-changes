"""Similarity metrics between two loaded features, computed in METRIC_CRS.

Every metric's interpretation is documented in docs/matching-behavior.md
section 3, including why iou_centroid_aligned is recorded but deliberately
NOT used as a classification gate (validated against real re-traced
buildings: it separates "positional" from "shape" disagreement, but does
not cleanly binary-separate "repositioned" from "reshaped").
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity

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


def _iou(geom_a, geom_b) -> float:
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

    iou = _iou(ga, gb)

    dx = ga.centroid.x - gb.centroid.x
    dy = ga.centroid.y - gb.centroid.y
    gb_aligned = affinity.translate(gb, xoff=dx, yoff=dy)
    iou_centroid_aligned = _iou(ga, gb_aligned)

    centroid_shift_m = ga.centroid.distance(gb.centroid)
    area_ratio = (gb.area / ga.area) if ga.area else 0.0
    hausdorff_m = ga.hausdorff_distance(gb)
    attrs_changed = tuple(tag for tag in SIGNIFICANT_TAGS if a.attrs.get(tag) != b.attrs.get(tag))

    return MatchMetrics(
        iou=iou,
        iou_centroid_aligned=iou_centroid_aligned,
        centroid_shift_m=centroid_shift_m,
        area_ratio=area_ratio,
        hausdorff_m=hausdorff_m,
        attrs_changed=attrs_changed,
    )
