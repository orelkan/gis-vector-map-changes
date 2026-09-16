from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.matching.pipeline import SnapshotRef, build_changeset_result, validate_comparable


def _ref(**overrides) -> SnapshotRef:
    base = {
        "id": 1,
        "source": "openstreetmap-ohsome",
        "layer": "building",
        "aoi_id": "tel-aviv-yafo",
        "aoi_version": "v1",
        "source_query_version": "v2",
        "requested_time": datetime(2026, 7, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return SnapshotRef(**base)


def _feature(osm_id, coords, building="house", category="residential", name=None, repair_method=None):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "osm_id": osm_id,
            "building": building,
            "category": category,
            "name": name,
            "repair_method": repair_method,
            "raw_tags": {"building": building},
        },
    }


_SQUARE_A = [[34.780, 32.080], [34.781, 32.080], [34.781, 32.081], [34.780, 32.081], [34.780, 32.080]]


# --- validate_comparable -------------------------------------------------


def test_validate_comparable_accepts_matching_snapshots():
    a = _ref(id=1, requested_time=datetime(2026, 6, 1, tzinfo=UTC))
    b = _ref(id=2, requested_time=datetime(2026, 7, 1, tzinfo=UTC))

    validate_comparable(a, b)  # must not raise


@pytest.mark.parametrize(
    "field,value",
    [
        ("aoi_version", "v2"),
        ("aoi_id", "some-other-aoi"),
        ("source_query_version", "v1"),
        ("layer", "road"),
        ("source", "overture"),
    ],
)
def test_validate_comparable_rejects_mismatched_field(field, value):
    a = _ref(id=1)
    b = _ref(id=2, **{field: value})

    with pytest.raises(ValueError, match=field):
        validate_comparable(a, b)


# --- build_changeset_result: end-to-end wiring ----------------------------


def test_build_changeset_result_end_to_end():
    snapshot_a = _ref(id=1, requested_time=datetime(2026, 6, 1, tzinfo=UTC))
    snapshot_b = _ref(id=2, requested_time=datetime(2026, 7, 1, tzinfo=UTC))

    geojson_a = {
        "type": "FeatureCollection",
        "features": [_feature("way/1", _SQUARE_A, building="house")],
    }
    geojson_b = {
        "type": "FeatureCollection",
        "features": [_feature("way/1", _SQUARE_A, building="office")],
    }

    result = build_changeset_result(snapshot_a, snapshot_b, geojson_a, geojson_b)

    assert result.counts["modified_attributes"] == 1
    assert sum(result.counts.values()) == 1
    assert len(result.records) == 1
    assert result.change_layer_geojson["type"] == "FeatureCollection"
    assert len(result.change_layer_geojson["features"]) == 1
    assert result.algorithm_version


def test_build_changeset_result_raises_on_incomparable_snapshots():
    snapshot_a = _ref(id=1, aoi_version="v1")
    snapshot_b = _ref(id=2, aoi_version="v2")
    empty = {"type": "FeatureCollection", "features": []}

    with pytest.raises(ValueError, match="aoi_version"):
        build_changeset_result(snapshot_a, snapshot_b, empty, empty)


def test_build_changeset_result_counts_sum_to_total_features():
    snapshot_a = _ref(id=1)
    snapshot_b = _ref(id=2)

    geojson_a = {
        "type": "FeatureCollection",
        "features": [
            _feature("way/1", _SQUARE_A),
            _feature(
                "way/gone",
                [[34.900, 32.200], [34.901, 32.200], [34.901, 32.201], [34.900, 32.201], [34.900, 32.200]],
            ),
        ],
    }
    geojson_b = {
        "type": "FeatureCollection",
        "features": [
            _feature("way/1", _SQUARE_A),
            _feature(
                "way/new",
                [[34.950, 32.250], [34.951, 32.250], [34.951, 32.251], [34.950, 32.251], [34.950, 32.250]],
            ),
        ],
    }

    result = build_changeset_result(snapshot_a, snapshot_b, geojson_a, geojson_b)

    # 2 features in A, 2 in B, one shared (way/1) -> 3 total records.
    assert sum(result.counts.values()) == 3
    assert result.counts["unchanged"] == 1
    assert result.counts["added"] == 1
    assert result.counts["removed"] == 1
