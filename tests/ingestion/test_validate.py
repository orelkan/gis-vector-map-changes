from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from src.ingestion import validate


def test_valid_polygon_is_passed_through_unchanged():
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])

    result = validate.validate_and_repair(polygon)

    assert result.original_valid is True
    assert result.repair_method is None
    assert result.repaired_valid is True
    assert result.geometry.equals(polygon)
    assert result.original_geometry.equals(polygon)


def test_polygon_with_hole_is_valid_and_unchanged():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]
    polygon = Polygon(outer, [hole])

    result = validate.validate_and_repair(polygon)

    assert result.original_valid is True
    assert result.repair_method is None
    assert result.geometry.equals(polygon)


def test_multipolygon_is_valid_and_unchanged():
    from shapely.geometry import MultiPolygon

    poly_a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    poly_b = Polygon([(2, 0), (3, 0), (3, 1), (2, 1), (2, 0)])
    multi = MultiPolygon([poly_a, poly_b])

    result = validate.validate_and_repair(multi)

    assert result.original_valid is True
    assert result.repair_method is None


def test_self_intersecting_bowtie_polygon_is_repaired():
    # "Bowtie": edges cross in the middle -- classic invalid-geometry case.
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    assert bowtie.is_valid is False  # sanity check on the fixture itself

    result = validate.validate_and_repair(bowtie)

    assert result.original_valid is False
    assert result.repair_method == validate.REPAIR_METHOD_MAKE_VALID
    assert result.repaired_valid is True
    assert result.geometry.is_valid is True
    # Original (invalid) geometry must be preserved separately, unmodified.
    assert result.original_geometry.equals(bowtie)
    assert not result.geometry.equals(result.original_geometry)


def test_repair_keeps_only_polygonal_parts():
    # A square with a zero-area "spike" along the top edge: make_valid
    # recovers the square but also emits the spike as a dangling LineString,
    # yielding a GeometryCollection. Reproduces the real shape of
    # relation/14011822 & relation/14011825 in the ingested Tel Aviv-Yafo
    # snapshots -- see docs/matching-behavior.md.
    spiked = Polygon([(0, 0), (10, 0), (10, 10), (15, 10), (10, 10), (0, 10), (0, 0)])
    assert spiked.is_valid is False

    from shapely.validation import make_valid

    assert make_valid(spiked).geom_type == "GeometryCollection"  # the problem we're fixing

    result = validate.validate_and_repair(spiked)

    # The invariant downstream matching (and a PostGIS polygonal column)
    # depends on: snapshots only ever contain Polygon/MultiPolygon.
    assert result.geometry.geom_type in validate.POLYGONAL_TYPES
    assert result.repair_method == validate.REPAIR_METHOD_MAKE_VALID_EXTRACT
    assert result.repaired_valid is True
    # The zero-area spike carried no area, so dropping it must not change area.
    assert result.geometry.area == pytest.approx(100.0)
    assert result.original_geometry.equals(spiked)


def test_repair_without_extraction_keeps_plain_method_label():
    # A bowtie repairs straight to a MultiPolygon -- nothing non-polygonal to
    # strip, so the method label must stay the plain one rather than claiming
    # an extraction that didn't happen.
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])

    result = validate.validate_and_repair(bowtie)

    assert result.geometry.geom_type in validate.POLYGONAL_TYPES
    assert result.repair_method == validate.REPAIR_METHOD_MAKE_VALID
