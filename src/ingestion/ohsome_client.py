"""Client for HeiGIT's ohsome API -- fetches OSM building geometries as they
existed at a given point in time, within our AOI.

IMPORTANT: this does NOT use the seemingly-obvious POST /elements/geometry
endpoint. That endpoint (and /elements/centroid) returned HTTP 403 when
tested live from two independent networks (a sandboxed dev environment and
a real home network), with identical requests to /elements/{bbox,count} and
/elementsFullHistory/geometry succeeding -- this looks like a real,
current, endpoint-specific restriction on ohsome's side, not an IP-based
anti-abuse fluke. No public explanation was found (checked ohsome's docs,
GitHub, and general search).

Workaround, verified live: POST /elementsFullHistory/geometry (see
https://docs.ohsome.org/ohsome-api/v1/ -- the "full history" endpoint
family, normally used to extract every version of matching features across
a time *range*) accepts a minimal-width range starting at our target
instant, e.g. `time=2026-07-01T00:00:00Z,2026-07-01T00:00:01Z`. ohsome
clips each returned version's `@validFrom`/`@validTo` to the query's
bounds, so every feature that existed (in matching form) at the range's
start comes back with `@validFrom` exactly equal to that start instant --
regardless of how long ago it was actually last edited. Filtering the
response down to `@validFrom == <requested instant>` (done in
src.ingestion.snapshot) therefore reconstructs the same "state at T"
result /elements/geometry would have given us. Verified against a live
control: for a fixed test bbox, this returned exactly the same feature
count as /elements/count (which is not blocked) for the same instant.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

OHSOME_BASE_URL = "https://api.ohsome.org/v1"
ELEMENTS_FULL_HISTORY_GEOMETRY_ENDPOINT = f"{OHSOME_BASE_URL}/elementsFullHistory/geometry"

# Width of the query range used for the point-in-time-via-clipping trick
# described above. Anything edited within this window after the target
# instant would appear as a spurious extra version with a later
# @validFrom -- and get filtered out anyway, since we only keep features
# whose @validFrom equals the requested instant exactly. 1 second is
# comfortably wide enough for ohsome's clipping behavior while keeping the
# "anything else in here is noise we discard" window negligible.
RANGE_WIDTH = timedelta(seconds=1)

# Deliberately requesting tags only, not full metadata -- ohsome can return
# contributor uid/user/changeset if asked, and CLAUDE.md's security rules
# say not to persist personal data we don't need.
BUILDING_FILTER = "building=* and geometry:polygon"
PROPERTIES = "tags"

DEFAULT_TIMEOUT_SECONDS = 300  # ohsome's own server-side timeout is 600s


def format_instant(instant: datetime) -> str:
    if instant.tzinfo is None:
        raise ValueError("requested_time must be timezone-aware")
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_request_payload(
    aoi_geometry: dict[str, Any],
    requested_time: datetime,
    *,
    filter_expression: str = BUILDING_FILTER,
    properties: str = PROPERTIES,
) -> dict[str, str]:
    """Build the form-encoded payload for a POST to /elementsFullHistory/geometry.

    Pure function, no network -- exact shape is asserted in tests. Raises
    ValueError if requested_time isn't timezone-aware, since a naive
    datetime here would silently mean "whatever timezone the caller forgot
    to set", which is exactly the kind of ambiguity a dated snapshot can't
    tolerate.
    """
    range_start = format_instant(requested_time)
    range_end = format_instant(requested_time + RANGE_WIDTH)

    bpolys = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": aoi_geometry}],
    }
    return {
        "bpolys": json.dumps(bpolys),
        "filter": filter_expression,
        "time": f"{range_start},{range_end}",
        "properties": properties,
    }


def fetch_building_geometries(
    aoi_geometry: dict[str, Any],
    requested_time: datetime,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call ohsome's /elementsFullHistory/geometry endpoint with a
    minimal-width range starting at requested_time.

    Returns the raw parsed GeoJSON FeatureCollection response, unfiltered,
    unvalidated, and unnormalized -- includes version-interval metadata
    (@validFrom/@validTo) for every feature touching the query range, not
    just the ones valid at requested_time. See
    src.ingestion.snapshot.build_snapshot_from_raw, which filters to
    @validFrom == requested_time before validating/normalizing.
    """
    payload = build_request_payload(aoi_geometry, requested_time)
    response = requests.post(
        ELEMENTS_FULL_HISTORY_GEOMETRY_ENDPOINT, data=payload, timeout=timeout
    )
    response.raise_for_status()
    return response.json()
