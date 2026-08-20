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
