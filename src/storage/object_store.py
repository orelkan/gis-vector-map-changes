"""Thin object-storage wrapper (MinIO, or anything else speaking the S3 API).

Takes an already-constructed boto3 S3 client rather than owning connection
setup itself -- the DAG task builds one from an Airflow Connection via
S3Hook(aws_conn_id=...).get_conn(); this module stays testable against a
plain boto3 client (real local MinIO, or a mocked one) without needing
Airflow.
"""

from __future__ import annotations

import json
from typing import Any


def put_json(s3_client: Any, bucket: str, key: str, data: dict) -> str:
    """Upload a JSON-serializable dict as an object. Returns its s3:// URI."""
    body = json.dumps(data).encode("utf-8")
    s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return f"s3://{bucket}/{key}"


def get_json(s3_client: Any, uri: str) -> dict:
    """Download and parse a JSON object given its s3://bucket/key URI --
    the inverse of put_json (which returns exactly this URI form).
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"expected an s3:// URI, got {uri!r}")
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read())


def snapshot_object_key(
    *,
    source: str,
    layer: str,
    aoi_id: str,
    aoi_version: str,
    requested_time_iso: str,
    kind: str,
) -> str:
    """Hive-style key layout, consistent across raw/processed objects.

    `kind` is "raw" or "processed".
    """
    if kind not in ("raw", "processed"):
        raise ValueError(f"kind must be 'raw' or 'processed', got {kind!r}")
    return (
        f"snapshots/source={source}/layer={layer}/"
        f"aoi={aoi_id}/aoi_version={aoi_version}/"
        f"requested_time={requested_time_iso}/{kind}.geojson"
    )


def changeset_object_key(
    *,
    source: str,
    layer: str,
    aoi_id: str,
    aoi_version: str,
    algorithm_version: str,
    requested_time_a_iso: str,
    requested_time_b_iso: str,
) -> str:
    """Hive-style key for a changeset's change-layer GeoJSON (every
    ChangeRecord as one FeatureCollection) -- mirrors snapshot_object_key's
    layout, keyed by the pair of snapshot instants being compared and the
    matching algorithm version that produced the comparison.
    """
    return (
        f"changesets/source={source}/layer={layer}/"
        f"aoi={aoi_id}/aoi_version={aoi_version}/"
        f"algorithm_version={algorithm_version}/"
        f"{requested_time_a_iso}_to_{requested_time_b_iso}/change_layer.geojson"
    )
