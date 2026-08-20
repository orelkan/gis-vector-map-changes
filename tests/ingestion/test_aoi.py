from __future__ import annotations

import json

import pytest
from shapely.geometry import shape

from src.ingestion.aoi import load_aoi


def test_load_aoi_reads_committed_tel_aviv_yafo_file():
    aoi = load_aoi()

    assert aoi.aoi_id == "tel-aviv-yafo"
    assert aoi.aoi_version == "v1"
    assert aoi.geometry["type"] == "Polygon"


def test_committed_aoi_geometry_is_valid_and_covers_tel_aviv():
    aoi = load_aoi()

    geometry = shape(aoi.geometry)
    assert geometry.is_valid

    # Sanity check: bounds should be roughly Tel Aviv-Yafo, not somewhere
    # else entirely (catches e.g. an accidental lon/lat swap).
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    assert 34.5 < min_lon < max_lon < 35.0
    assert 31.9 < min_lat < max_lat < 32.3


def test_committed_aoi_records_provenance():
    aoi = load_aoi()

    assert aoi.properties["source"] == "OpenStreetMap relation 1382494"
    assert aoi.properties["license"] == "Open Database License (ODbL) v1.0"
    assert "retrieved_at" in aoi.properties


def test_load_aoi_raises_on_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.geojson"

    with pytest.raises(FileNotFoundError):
        load_aoi(missing_path)


def test_load_aoi_raises_on_missing_required_property(tmp_path):
    bad_file = tmp_path / "bad_aoi.geojson"
    bad_file.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"aoi_id": "x"},  # missing aoi_version
                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    }
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="aoi_version"):
        load_aoi(bad_file)


def test_load_aoi_raises_on_wrong_feature_count(tmp_path):
    bad_file = tmp_path / "bad_aoi.geojson"
    bad_file.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    with pytest.raises(ValueError, match="exactly one Feature"):
        load_aoi(bad_file)
