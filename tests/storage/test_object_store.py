from __future__ import annotations

import json

import pytest

from src.storage import object_store


class FakeS3Client:
    """Minimal stand-in for a boto3 S3 client's put_object/get_object --
    avoids taking a moto/boto3-testing dependency just to check we call it
    correctly.
    """

    def __init__(self):
        self.calls = []
        self._objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.calls.append(
            {"bucket": Bucket, "key": Key, "body": Body, "content_type": ContentType}
        )
        self._objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        import io

        body = self._objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body)}


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


def test_get_json_downloads_and_parses():
    client = FakeS3Client()
    data = {"type": "FeatureCollection", "features": [{"a": 1}]}
    uri = object_store.put_json(client, "my-bucket", "some/key.geojson", data)

    result = object_store.get_json(client, uri)

    assert result == data


def test_get_json_rejects_non_s3_uri():
    client = FakeS3Client()

    with pytest.raises(ValueError, match="s3://"):
        object_store.get_json(client, "https://example.com/not-s3.json")


def test_changeset_object_key_layout():
    key = object_store.changeset_object_key(
        source="openstreetmap-ohsome",
        layer="building",
        aoi_id="tel-aviv-yafo",
        aoi_version="v1",
        algorithm_version="v1",
        requested_time_a_iso="2026-06-01T00:00:00Z",
        requested_time_b_iso="2026-07-01T00:00:00Z",
    )

    assert key == (
        "changesets/source=openstreetmap-ohsome/layer=building/"
        "aoi=tel-aviv-yafo/aoi_version=v1/"
        "algorithm_version=v1/"
        "2026-06-01T00:00:00Z_to_2026-07-01T00:00:00Z/change_layer.geojson"
    )
