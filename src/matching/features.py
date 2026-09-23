"""Loads a snapshot's processed GeoJSON into the internal representation
matching works with: geometry reprojected to METRIC_CRS, keyed by osm_id,
carrying only the attributes matching actually looks at.

Deliberately Airflow-independent and I/O-free (CLAUDE.md: "Business-logic
functions should be runnable and testable without Airflow") -- callers pass
an already-fetched GeoJSON dict, the same split used in
src.ingestion.snapshot.build_snapshot_from_raw.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from src.matching.config import SIGNIFICANT_TAGS
from src.matching.crs import to_metric


@dataclass(frozen=True)
class LoadedFeature:
    osm_id: str
    geometry: BaseGeometry  # reprojected to METRIC_CRS
    attrs: dict[str, str | None]  # exactly SIGNIFICANT_TAGS, nothing else
    repaired: bool  # True if ingestion's repair_method was set for this feature


def load_feature(geojson_feature: dict[str, Any]) -> LoadedFeature:
    """Load one already-normalized feature (as produced by
    src.ingestion.snapshot.normalize_feature) into matching's representation.
    """
    props = geojson_feature["properties"]
    return LoadedFeature(
        osm_id=props["osm_id"],
        geometry=to_metric(shape(geojson_feature["geometry"])),
        attrs={tag: props.get(tag) for tag in SIGNIFICANT_TAGS},
        repaired=props.get("repair_method") is not None,
    )


def load_features(processed_geojson: dict[str, Any]) -> dict[str, LoadedFeature]:
    """Load an entire processed-snapshot FeatureCollection.

    Raises ValueError on a duplicate osm_id within one snapshot -- that
    would silently corrupt the 1:1 keying every later stage relies on, so
    it must fail loudly rather than let the second copy overwrite the first.
    """
    loaded: dict[str, LoadedFeature] = {}
    for raw_feature in processed_geojson.get("features", []):
        feature = load_feature(raw_feature)
        if feature.osm_id in loaded:
            raise ValueError(f"duplicate osm_id in snapshot: {feature.osm_id!r}")
        loaded[feature.osm_id] = feature
    return loaded
