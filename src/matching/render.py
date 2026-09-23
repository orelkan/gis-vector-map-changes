"""Renders ChangeRecords into a GeoJSON "change layer" FeatureCollection --
the deliverable CLAUDE.md's MVP output section calls for.

Pure function: takes already-loaded features (in METRIC_CRS) and reprojects
back to OGC:CRS84 for the output, matching every other GeoJSON artifact this
project produces (CLAUDE.md: record CRS metadata at dataset boundaries).
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import mapping
from shapely.ops import unary_union

from src.matching.changeset import ChangeRecord
from src.matching.config import ALGORITHM_VERSION
from src.matching.crs import to_crs84
from src.matching.features import LoadedFeature
from src.matching.metrics import MatchMetrics


def _metrics_dict(metrics: MatchMetrics) -> dict[str, Any]:
    return {
        "iou": metrics.iou,
        "iou_centroid_aligned": metrics.iou_centroid_aligned,
        "centroid_shift_m": metrics.centroid_shift_m,
        "area_ratio": metrics.area_ratio,
        "hausdorff_m": metrics.hausdorff_m,
        "attrs_changed": list(metrics.attrs_changed),
    }


def _record_geometry(record: ChangeRecord, features_a: dict, features_b: dict):
    """One representative geometry per record. For a resolved 1:1 pair this
    is unambiguous (B's geometry -- the "current" state -- or A's for a
    removal). For an ambiguous multi-candidate group there is no single
    right answer, so the union of every involved footprint is used: still
    locates the record on a map, while every individual geometry and its
    per-pair metrics remain available in `properties.candidates`.
    """
    geoms = [features_b[oid].geometry for oid in record.osm_ids_b]
    geoms += [features_a[oid].geometry for oid in record.osm_ids_a if not record.osm_ids_b]
    if len(geoms) == 1:
        return geoms[0]
    return unary_union(geoms)


def render_change_layer(
    records: list[ChangeRecord],
    features_a: dict[str, LoadedFeature],
    features_b: dict[str, LoadedFeature],
) -> dict[str, Any]:
    """Builds the change-layer FeatureCollection for one changeset."""
    geojson_features = []
    for record in records:
        geometry = _record_geometry(record, features_a, features_b)
        reprojected = to_crs84(geometry)

        candidates = [
            {"osm_id_a": a_id, "osm_id_b": b_id, **_metrics_dict(metrics)}
            for (a_id, b_id), metrics in record.pair_metrics.items()
        ]

        geojson_features.append(
            {
                "type": "Feature",
                "geometry": mapping(reprojected),
                "properties": {
                    "classification": record.classification,
                    "match_method": record.match_method,
                    "match_score": record.match_score,
                    "classification_reason": record.classification_reason,
                    "osm_ids_a": list(record.osm_ids_a),
                    "osm_ids_b": list(record.osm_ids_b),
                    "involves_repaired_geometry": record.involves_repaired_geometry,
                    "touches_aoi_boundary": record.touches_aoi_boundary,
                    "algorithm_version": ALGORITHM_VERSION,
                    "candidates": candidates,
                },
            }
        )

    return {"type": "FeatureCollection", "features": geojson_features}
