"""Orchestrates one snapshot: fetch from ohsome, validate/repair geometry,
normalize attributes.

Deliberately Airflow-independent (CLAUDE.md: "Business-logic functions
should be runnable and testable without Airflow") and deliberately does not
persist anything itself -- see src.storage.object_store / src.db.snapshots
for that, and dags/ingest_osm_building_snapshots.py for how the DAG task
wires fetch -> persist together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import mapping, shape

from src.ingestion import building_category, ohsome_client, validate
from src.ingestion.aoi import Aoi

SOURCE = "openstreetmap-ohsome"
LAYER = "building"
CRS = "OGC:CRS84"  # WGS84, lon-lat order -- see ohsome API boundaries docs


@dataclass(frozen=True)
class SnapshotResult:
    source: str
    source_query_version: str
    layer: str
    aoi_id: str
    aoi_version: str
    requested_time: datetime
    crs: str
    raw_geojson: dict[str, Any]
    processed_geojson: dict[str, Any]
    feature_count: int
    invalid_geometry_count: int
    repaired_geometry_count: int


def _parse_osm_id(osm_id: str) -> tuple[str, str]:
    osm_type, _, osm_ref = osm_id.partition("/")
    return osm_type, osm_ref


def normalize_feature(raw_feature: dict[str, Any]) -> dict[str, Any]:
    """Validate/repair one raw ohsome feature and normalize its attributes
    into our own documented shape (see building_category.py for the
    category mapping, validate.py for repair semantics).
    """
    props = raw_feature.get("properties", {})
    osm_id = props.get("@osmId", "")
    osm_type, osm_ref = _parse_osm_id(osm_id)

    geometry = shape(raw_feature["geometry"])
    result = validate.validate_and_repair(geometry)

    building_tag = props.get("building")
    category = building_category.categorize(building_tag)

    return {
        "type": "Feature",
        "geometry": mapping(result.geometry),
        "properties": {
            "osm_id": osm_id,
            "osm_type": osm_type,
            "osm_ref": osm_ref,
            "building": building_tag,
            "category": category,
            "name": props.get("name"),
            "raw_tags": {k: v for k, v in props.items() if not k.startswith("@")},
            "original_valid": result.original_valid,
            "repair_method": result.repair_method,
            "repaired_valid": result.repaired_valid,
            "original_geometry": mapping(result.original_geometry),
        },
    }


def build_snapshot_from_raw(
    raw_geojson: dict[str, Any],
    *,
    aoi: Aoi,
    requested_time: datetime,
    source_query_version: str,
) -> SnapshotResult:
    """Validate/normalize an already-fetched raw ohsome response.

    Split out from build_snapshot() so tests can exercise the
    validate/normalize logic with a fixture response, with no network call.
    """
    processed_features = []
    invalid_count = 0
    repaired_count = 0

    for raw_feature in raw_geojson.get("features", []):
        feature = normalize_feature(raw_feature)
        processed_features.append(feature)
        if not feature["properties"]["original_valid"]:
            invalid_count += 1
        if feature["properties"]["repair_method"] is not None:
            repaired_count += 1

    return SnapshotResult(
        source=SOURCE,
        source_query_version=source_query_version,
        layer=LAYER,
        aoi_id=aoi.aoi_id,
        aoi_version=aoi.aoi_version,
        requested_time=requested_time,
        crs=CRS,
        raw_geojson=raw_geojson,
        processed_geojson={"type": "FeatureCollection", "features": processed_features},
        feature_count=len(processed_features),
        invalid_geometry_count=invalid_count,
        repaired_geometry_count=repaired_count,
    )


def build_snapshot(
    aoi: Aoi,
    requested_time: datetime,
    *,
    source_query_version: str,
) -> SnapshotResult:
    """Fetch from ohsome, then validate/normalize. See build_snapshot_from_raw
    for the network-free half of this, which is what most tests should use.
    """
    raw_geojson = ohsome_client.fetch_building_geometries(aoi.geometry, requested_time)
    return build_snapshot_from_raw(
        raw_geojson,
        aoi=aoi,
        requested_time=requested_time,
        source_query_version=source_query_version,
    )
