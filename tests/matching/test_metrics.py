from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from src.matching.features import LoadedFeature
from src.matching.metrics import compute_metrics


def _feat(geom, building="house", category="residential", name=None, repaired=False):
    return LoadedFeature(
        osm_id="test",
        geometry=geom,
        attrs={"building": building, "category": category, "name": name},
        repaired=repaired,
    )


def _square(x0, y0, side):
    return Polygon([(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)])


def test_identical_geometry_gives_iou_1_and_zero_shift():
    sq = _square(0, 0, 10)
    m = compute_metrics(_feat(sq), _feat(sq))

    assert m.iou == pytest.approx(1.0)
    assert m.iou_centroid_aligned == pytest.approx(1.0)
    assert m.centroid_shift_m == pytest.approx(0.0)
    assert m.area_ratio == pytest.approx(1.0)
    assert m.hausdorff_m == pytest.approx(0.0)


def test_disjoint_geometry_gives_iou_0():
    a = _square(0, 0, 1)
    b = _square(100, 100, 1)

    m = compute_metrics(_feat(a), _feat(b))

    assert m.iou == pytest.approx(0.0)


def test_known_partial_overlap_iou():
    # B (1x1, at origin) sits entirely inside A (2x2, at origin):
    # intersection = B's area = 1, union = A's area = 4 -> IoU = 0.25.
    a = _square(0, 0, 2)
    b = _square(0, 0, 1)

    m = compute_metrics(_feat(a), _feat(b))

    assert m.iou == pytest.approx(0.25)
    assert m.area_ratio == pytest.approx(1 / 4)
    # centroid of A=(1,1), of B=(0.5,0.5) -> shift = sqrt(0.5^2+0.5^2)
    assert m.centroid_shift_m == pytest.approx(0.5 * 2**0.5)


def test_pure_translation_is_recovered_by_centroid_alignment():
    # Same shape, moved far away: position-sensitive IoU collapses, but
    # aligning centroids first must recover IoU=1 -- this is exactly the
    # real-world case (a re-traced building block) that justified adding
    # iou_centroid_aligned. See docs/matching-spec.md section 3.
    a = _square(0, 0, 10)
    b = _square(500, 500, 10)  # identical shape, far away -> disjoint

    m = compute_metrics(_feat(a), _feat(b))

    assert m.iou == pytest.approx(0.0)
    assert m.iou_centroid_aligned == pytest.approx(1.0)
    assert m.centroid_shift_m == pytest.approx(500 * 2**0.5)


def test_hausdorff_distance_for_near_point_geometries():
    # Two tiny squares are effectively points; Hausdorff distance between
    # two points is their Euclidean distance -- a 3-4-5 triangle.
    a = _square(0, 0, 0.0001)
    b = _square(3, 4, 0.0001)

    m = compute_metrics(_feat(a), _feat(b))

    assert m.hausdorff_m == pytest.approx(5.0, abs=0.001)


def test_attrs_changed_detects_only_differing_significant_tags():
    a = _feat(_square(0, 0, 1), building="house", category="residential", name="Old")
    b = _feat(_square(0, 0, 1), building="house", category="residential", name="New")

    m = compute_metrics(a, b)

    assert m.attrs_changed == ("name",)


def test_attrs_changed_empty_when_all_significant_tags_match():
    a = _feat(_square(0, 0, 1), building="house", category="residential", name="Same")
    b = _feat(_square(0, 0, 1), building="house", category="residential", name="Same")

    m = compute_metrics(a, b)

    assert m.attrs_changed == ()


def test_attrs_changed_can_report_multiple_tags():
    a = _feat(_square(0, 0, 1), building="house", category="residential", name="A")
    b = _feat(_square(0, 0, 1), building="office", category="commercial", name="A")

    m = compute_metrics(a, b)

    assert set(m.attrs_changed) == {"building", "category"}
