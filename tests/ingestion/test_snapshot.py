from __future__ import annotations

from datetime import UTC, datetime

from src.ingestion import building_category as bc
from src.ingestion.aoi import Aoi
from src.ingestion.snapshot import build_snapshot_from_raw, normalize_feature

TEST_AOI = Aoi(
    aoi_id="tel-aviv-yafo",
    aoi_version="v1",
    geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
    properties={},
)


def _feature_by_osm_id(result, osm_id):
    matches = [
        f for f in result.processed_geojson["features"] if f["properties"]["osm_id"] == osm_id
    ]
    assert len(matches) == 1, f"expected exactly one feature with osm_id={osm_id}"
    return matches[0]


def test_normalize_feature_parses_osm_type_and_ref():
    raw = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        "properties": {"@osmId": "way/12345", "@snapshotTimestamp": "2026-07-01T00:00:00Z"},
    }

    feature = normalize_feature(raw)

    assert feature["properties"]["osm_id"] == "way/12345"
    assert feature["properties"]["osm_type"] == "way"
    assert feature["properties"]["osm_ref"] == "12345"


def test_build_snapshot_from_raw_counts(ohsome_response_fixture):
    result = build_snapshot_from_raw(
        ohsome_response_fixture,
        aoi=TEST_AOI,
        requested_time=datetime(2026, 7, 1, tzinfo=UTC),
        source_query_version="v1",
    )

    assert result.feature_count == 4
    assert result.invalid_geometry_count == 1
    assert result.repaired_geometry_count == 1
    assert result.source == "openstreetmap-ohsome"
    assert result.layer == "building"
    assert result.aoi_id == "tel-aviv-yafo"
    assert result.crs == "OGC:CRS84"


def test_build_snapshot_from_raw_category_assignment(ohsome_response_fixture):
    result = build_snapshot_from_raw(
        ohsome_response_fixture,
        aoi=TEST_AOI,
        requested_time=datetime(2026, 7, 1, tzinfo=UTC),
        source_query_version="v1",
    )

    house = _feature_by_osm_id(result, "way/100000001")
    assert house["properties"]["category"] == bc.CATEGORY_RESIDENTIAL
    assert house["properties"]["name"] == "Test House"

    apartments = _feature_by_osm_id(result, "way/100000002")
    assert apartments["properties"]["category"] == bc.CATEGORY_RESIDENTIAL
    assert apartments["properties"]["name"] is None

    generic_yes = _feature_by_osm_id(result, "way/100000003")
    assert generic_yes["properties"]["category"] == bc.CATEGORY_OTHER

    synagogue = _feature_by_osm_id(result, "relation/100000004")
    assert synagogue["properties"]["osm_type"] == "relation"
    assert synagogue["properties"]["category"] == bc.CATEGORY_RELIGIOUS


def test_build_snapshot_from_raw_repairs_invalid_geometry_and_keeps_original(
    ohsome_response_fixture,
):
    result = build_snapshot_from_raw(
        ohsome_response_fixture,
        aoi=TEST_AOI,
        requested_time=datetime(2026, 7, 1, tzinfo=UTC),
        source_query_version="v1",
    )

    invalid_feature = _feature_by_osm_id(result, "way/100000003")
    props = invalid_feature["properties"]

    assert props["original_valid"] is False
    assert props["repair_method"] == "make_valid"
    assert props["repaired_valid"] is True
    assert props["original_geometry"] != invalid_feature["geometry"]


def test_build_snapshot_from_raw_preserves_raw_tags_without_metadata_fields(
    ohsome_response_fixture,
):
    result = build_snapshot_from_raw(
        ohsome_response_fixture,
        aoi=TEST_AOI,
        requested_time=datetime(2026, 7, 1, tzinfo=UTC),
        source_query_version="v1",
    )

    house = _feature_by_osm_id(result, "way/100000001")
    raw_tags = house["properties"]["raw_tags"]

    assert raw_tags == {"building": "house", "name": "Test House"}
    assert not any(key.startswith("@") for key in raw_tags)
