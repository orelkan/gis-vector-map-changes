"""Client for HeiGIT's ohsome API -- fetches OSM building geometries as they
existed at a given point in time, within our AOI.

See https://docs.ohsome.org/ohsome-api/v1/ -- specifically POST
/elements/geometry, which returns a GeoJSON FeatureCollection of features
matching a tag filter as they existed at a given timestamp, clipped/filtered
to a spatial boundary (`bpolys`, a GeoJSON polygon).

NOTE: verified live against the real API from this project's dev sandbox
that GET /v1/metadata and /v1/elements/{bbox,count} work, but
/v1/elements/{geometry,centroid} returned HTTP 403 from that specific
network -- most likely a WAF/anti-abuse rule on the sandbox's shared egress
IP, not a real API restriction (the endpoint is documented and is the
correct one for real footprint geometry, unlike /elements/bbox which only
returns each feature's bounding rectangle). Re-verify from your own network
before the first real run; see the plan doc.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import requests

OHSOME_BASE_URL = "https://api.ohsome.org/v1"
ELEMENTS_GEOMETRY_ENDPOINT = f"{OHSOME_BASE_URL}/elements/geometry"

# Deliberately requesting tags only, not full metadata -- ohsome can return
# contributor uid/user/changeset if asked, and CLAUDE.md's security rules
# say not to persist personal data we don't need.
BUILDING_FILTER = "building=* and geometry:polygon"
PROPERTIES = "tags"

DEFAULT_TIMEOUT_SECONDS = 300  # ohsome's own server-side timeout is 600s


def build_request_payload(
    aoi_geometry: dict[str, Any],
    requested_time: datetime,
    *,
    filter_expression: str = BUILDING_FILTER,
    properties: str = PROPERTIES,
) -> dict[str, str]:
    """Build the form-encoded payload for a POST to /elements/geometry.

    Pure function, no network -- exact shape is asserted in tests.
    Raises ValueError if requested_time isn't timezone-aware, since a naive
    datetime here would silently mean "whatever timezone the caller forgot
    to set", which is exactly the kind of ambiguity a dated snapshot can't
    tolerate.
    """
    if requested_time.tzinfo is None:
        raise ValueError("requested_time must be timezone-aware")
    utc_time = requested_time.astimezone(UTC)

    bpolys = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": aoi_geometry}],
    }
    return {
        "bpolys": json.dumps(bpolys),
        "filter": filter_expression,
        "time": utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "properties": properties,
    }


def fetch_building_geometries(
    aoi_geometry: dict[str, Any],
    requested_time: datetime,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call ohsome's /elements/geometry endpoint.

    Returns the raw parsed GeoJSON FeatureCollection response, unvalidated
    and unnormalized -- see src.ingestion.snapshot for that.
    """
    payload = build_request_payload(aoi_geometry, requested_time)
    response = requests.post(ELEMENTS_GEOMETRY_ENDPOINT, data=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
