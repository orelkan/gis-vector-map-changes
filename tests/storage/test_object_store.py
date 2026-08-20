from __future__ import annotations

import json

import pytest

from src.storage import object_store


class FakeS3Client:
    """Minimal stand-in for a boto3 S3 client's put_object -- avoids taking
    a moto/boto3-testing dependency just to check we call it correctly.
    """

    def __init__(self):
        self.calls = []

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.calls.append(
            {"bucket": Bucket, "key": Key, "body": Body, "content_type": ContentType}
        )


def test_snapshot_object_key_layout():
    key = object_store.snapshot_object_key(
        source="openstreetmap-ohsome",
        layer="building",
        aoi_id="tel-aviv-yafo",
        aoi_version="v1",
        requested_time_iso="2026-07-01T00:00:00Z",
        kind="raw",
    )

    assert key == (
        "snapshots/source=openstreetmap-ohsome/layer=building/"
        "aoi=tel-aviv-yafo/aoi_version=v1/"
        "requested_time=2026-07-01T00:00:00Z/raw.geojson"
    )


def test_snapshot_object_key_rejects_invalid_kind():
    with pytest.raises(ValueError, match="kind"):
        object_store.snapshot_object_key(
            source="s",
            layer="l",
            aoi_id="a",
            aoi_version="v1",
            requested_time_iso="2026-07-01T00:00:00Z",
            kind="not-raw-or-processed",
        )


def test_put_json_uploads_and_returns_uri():
    client = FakeS3Client()
    data = {"type": "FeatureCollection", "features": []}

    uri = object_store.put_json(client, "my-bucket", "some/key.geojson", data)

    assert uri == "s3://my-bucket/some/key.geojson"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["bucket"] == "my-bucket"
    assert call["key"] == "some/key.geojson"
    assert call["content_type"] == "application/json"
    assert json.loads(call["body"]) == data
