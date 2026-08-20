"""Load the committed, versioned Tel Aviv-Yafo area-of-interest polygon.

Per CLAUDE.md: "Store the authoritative area of interest as a versioned
GeoJSON polygon. Do not treat a casually typed bounding box as the permanent
AOI." The AOI file itself (aoi/tel_aviv_yafo_v1.geojson) carries its
provenance (source, retrieval method/date, license) in its GeoJSON
properties.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# src/ingestion/aoi.py -> src/ingestion -> src -> repo root -> aoi/
DEFAULT_AOI_PATH = Path(__file__).resolve().parents[2] / "aoi" / "tel_aviv_yafo_v1.geojson"


@dataclass(frozen=True)
class Aoi:
    aoi_id: str
    aoi_version: str
    geometry: dict[str, Any]  # GeoJSON geometry (Polygon/MultiPolygon), WGS84
    properties: dict[str, Any]  # full provenance properties, for logging/reference


def load_aoi(path: Path = DEFAULT_AOI_PATH) -> Aoi:
    """Load the versioned AOI GeoJSON file and return its geometry + identity.

    Fails loudly (FileNotFoundError / ValueError) rather than silently
    falling back to something else -- an ingestion run must use exactly the
    AOI it thinks it's using.
    """
    data = json.loads(path.read_text())
    features = data.get("features", [])
    if len(features) != 1:
        raise ValueError(f"Expected exactly one Feature in AOI file {path}, found {len(features)}")

    feature = features[0]
    properties = feature.get("properties", {})
    for required in ("aoi_id", "aoi_version"):
        if required not in properties:
            raise ValueError(f"AOI file {path} is missing required property '{required}'")

    return Aoi(
        aoi_id=properties["aoi_id"],
        aoi_version=properties["aoi_version"],
        geometry=feature["geometry"],
        properties=properties,
    )
