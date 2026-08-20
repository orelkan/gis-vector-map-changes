from __future__ import annotations

import json
from datetime import UTC, datetime, timezone

import pytest

from src.ingestion import ohsome_client

AOI_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[34.7, 32.0], [34.9, 32.0], [34.9, 32.2], [34.7, 32.2], [34.7, 32.0]]],
}


def test_build_request_payload_shape():
    requested_time = datetime(2026, 7, 1, tzinfo=UTC)

    payload = ohsome_client.build_request_payload(AOI_GEOMETRY, requested_time)

    assert payload["filter"] == "building=* and geometry:polygon"
    assert payload["time"] == "2026-07-01T00:00:00Z"
    assert payload["properties"] == "tags"

    bpolys = json.loads(payload["bpolys"])
    assert bpolys["type"] == "FeatureCollection"
    assert bpolys["features"][0]["geometry"] == AOI_GEOMETRY


def test_build_request_payload_converts_to_utc():
    from datetime import timedelta

    tz_plus_3 = timezone(timedelta(hours=3))
    requested_time = datetime(2026, 7, 1, 3, 0, 0, tzinfo=tz_plus_3)  # == 2026-07-01T00:00:00Z

    payload = ohsome_client.build_request_payload(AOI_GEOMETRY, requested_time)

    assert payload["time"] == "2026-07-01T00:00:00Z"


def test_build_request_payload_rejects_naive_datetime():
    naive_time = datetime(2026, 7, 1)  # noqa: DTZ001 -- deliberately naive, that's what's under test

    with pytest.raises(ValueError, match="timezone-aware"):
        ohsome_client.build_request_payload(AOI_GEOMETRY, naive_time)


def test_build_request_payload_custom_filter():
    requested_time = datetime(2026, 7, 1, tzinfo=UTC)

    payload = ohsome_client.build_request_payload(
        AOI_GEOMETRY, requested_time, filter_expression="building=house"
    )

    assert payload["filter"] == "building=house"
