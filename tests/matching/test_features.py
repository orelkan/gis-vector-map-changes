from __future__ import annotations

import pytest

from src.matching import features

SQUARE_1DEG = {
    "type": "Polygon",
    "coordinates": [[[34.78, 32.08], [34.781, 32.08], [34.781, 32.081], [34.78, 32.081], [34.78, 32.08]]],
}


def _feature(osm_id="way/1", building="house", category="residential", name="Test",
             repair_method=None, geometry=None):
    return {
        "type": "Feature",
        "geometry": geometry or SQUARE_1DEG,
        "properties": {
            "osm_id": osm_id,
            "building": building,
            "category": category,
            "name": name,
            "repair_method": repair_method,
            "raw_tags": {"building": building},
        },
    }


def test_load_feature_reprojects_to_metric_crs():
    loaded = features.load_feature(_feature())

    # EPSG:2039 (Israeli TM Grid) puts Tel Aviv-Yafo's coordinates in the
    # low hundreds-of-thousands of metres, nothing like raw lon/lat degrees.
    minx, miny, _maxx, _maxy = loaded.geometry.bounds
    assert 100_000 < minx < 300_000
    assert 500_000 < miny < 800_000


def test_load_feature_extracts_only_significant_tags():
    loaded = features.load_feature(_feature(building="house", category="residential", name="Test"))

    assert loaded.attrs == {"building": "house", "category": "residential", "name": "Test"}


def test_load_feature_repaired_flag_from_repair_method():
    assert features.load_feature(_feature(repair_method=None)).repaired is False
    assert features.load_feature(_feature(repair_method="make_valid")).repaired is True


def test_load_features_keys_by_osm_id():
    fc = {"type": "FeatureCollection", "features": [_feature("way/1"), _feature("way/2")]}

    loaded = features.load_features(fc)

    assert set(loaded) == {"way/1", "way/2"}


def test_load_features_rejects_duplicate_osm_id():
    fc = {"type": "FeatureCollection", "features": [_feature("way/1"), _feature("way/1")]}

    with pytest.raises(ValueError, match="duplicate osm_id"):
        features.load_features(fc)


def test_load_features_empty_collection():
    assert features.load_features({"type": "FeatureCollection", "features": []}) == {}
