"""Reprojection between the storage CRS and the metric CRS used for matching.

Snapshots are stored in OGC:CRS84 (see src.ingestion.snapshot.CRS); every
metric must be computed in a projected CRS instead (CLAUDE.md: never
calculate metric distance or area directly in EPSG:4326). Both directions
live here so the transformers are built once, and so the
repair-after-reprojection rule below is applied consistently rather than
being remembered at each call site.
"""

from __future__ import annotations

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from src.matching.config import METRIC_CRS

STORAGE_CRS = "OGC:CRS84"

# always_xy=True keeps lon,lat / x,y order, matching GeoJSON's coordinate
# order.
_TO_METRIC = Transformer.from_crs(STORAGE_CRS, METRIC_CRS, always_xy=True)
_TO_STORAGE = Transformer.from_crs(METRIC_CRS, STORAGE_CRS, always_xy=True)


def to_metric(geometry: BaseGeometry) -> BaseGeometry:
    """Reproject a stored (OGC:CRS84) geometry into METRIC_CRS.

    A geometry valid in CRS84 is not guaranteed valid after reprojection
    (precision/topology can shift at extreme scale, though not expected at
    this AOI's size) -- repair defensively rather than let an invalid
    geometry silently propagate into every downstream metric.
    """
    reprojected = shapely_transform(_TO_METRIC.transform, geometry)
    return reprojected if reprojected.is_valid else reprojected.buffer(0)


def to_crs84(geometry: BaseGeometry) -> BaseGeometry:
    """Reproject a METRIC_CRS geometry back to OGC:CRS84 for output,
    matching every other GeoJSON artifact this project produces (CLAUDE.md:
    record CRS metadata at dataset boundaries).
    """
    return shapely_transform(_TO_STORAGE.transform, geometry)
