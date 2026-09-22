"""Publish ingested snapshots and computed changesets from MinIO into the
PostGIS serving tables that back the web UI's vector tiles.

Orchestration only, per CLAUDE.md's architecture rules -- the loading logic
lives in src/publish/postgis.py and is independently testable without
Airflow (see tests/publish/). This DAG wires: look up metadata -> fetch
GeoJSON from MinIO -> publish rows.

MinIO remains the immutable store of record; PostGIS is a *derived* serving
layer, rebuildable at any time by re-running this DAG. Publishing is
idempotent (atomic delete-then-insert scoped to one snapshot/changeset).

Task ordering matters and is enforced structurally: change records derive
their before/after geometry by joining to already-published snapshot rows,
so publish_snapshot must complete for both of a changeset's snapshots before
publish_changeset runs. src/publish/postgis.py also checks this at runtime
and raises rather than writing NULL geometry.

Manually triggered (schedule=None) for consistency with the other two DAGs.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Param, dag, get_current_context, task

from src.db import changesets as changesets_db
from src.db import snapshots as snapshots_db
from src.publish import postgis
from src.storage import object_store

log = logging.getLogger(__name__)

# Every snapshot currently ingested (see ingest_osm_building_snapshots).
DEFAULT_REQUESTED_TIMES = [
    "2021-07-01T00:00:00Z",
    "2022-07-01T00:00:00Z",
    "2023-07-01T00:00:00Z",
    "2024-07-01T00:00:00Z",
    "2025-07-01T00:00:00Z",
    "2026-06-01T00:00:00Z",
    "2026-07-01T00:00:00Z",
]

# Every changeset currently computed (see build_changesets).
DEFAULT_COMPARISON_PAIRS = [
    {"requested_time_a": "2026-06-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2025-07-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2021-07-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2021-07-01T00:00:00Z", "requested_time_b": "2022-07-01T00:00:00Z"},
    {"requested_time_a": "2022-07-01T00:00:00Z", "requested_time_b": "2023-07-01T00:00:00Z"},
    {"requested_time_a": "2023-07-01T00:00:00Z", "requested_time_b": "2024-07-01T00:00:00Z"},
    {"requested_time_a": "2024-07-01T00:00:00Z", "requested_time_b": "2025-07-01T00:00:00Z"},
]

AWS_CONN_ID = os.environ.get("MINIO_AIRFLOW_CONN_ID", "minio_default")
POSTGRES_CONN_ID = os.environ.get("GIS_POSTGRES_AIRFLOW_CONN_ID", "gis_postgres_default")


def _parse_instant(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _natural_key(params: dict, requested_time_str: str) -> dict:
    return {
        "source": params["source"],
        "layer": params["layer"],
        "aoi_id": params["aoi_id"],
        "aoi_version": params["aoi_version"],
        "source_query_version": params["source_query_version"],
        "requested_time": _parse_instant(requested_time_str),
    }


@dag(
    dag_id="publish_to_postgis",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    tags=["publish", "postgis", "web"],
    params={
        "requested_times": Param(
            DEFAULT_REQUESTED_TIMES,
            type="array",
            description="Snapshot instants to publish into snapshot_features.",
        ),
        "comparison_pairs": Param(
            DEFAULT_COMPARISON_PAIRS,
            type="array",
            description="Changesets to publish into change_features. Both snapshots of "
            "each pair must also appear in requested_times (or already be published).",
        ),
        "source": Param("openstreetmap-ohsome", type="string"),
        "layer": Param("building", type="string"),
        "aoi_id": Param("tel-aviv-yafo", type="string"),
        "aoi_version": Param("v1", type="string"),
        "source_query_version": Param("v2", type="string"),
        "algorithm_version": Param(
            "v1",
            type="string",
            description="Which matching algorithm version's changesets to publish.",
        ),
    },
)
def publish_to_postgis():
    @task
    def get_requested_times() -> list[str]:
        return get_current_context().get("params", {})["requested_times"]

    @task
    def get_comparison_pairs() -> list[dict]:
        return get_current_context().get("params", {})["comparison_pairs"]

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(minutes=15))
    def publish_snapshot(requested_time_str: str) -> dict:
        params = get_current_context().get("params", {})
        pg_conn = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).get_conn()
        s3_client = S3Hook(aws_conn_id=AWS_CONN_ID).get_conn()

        natural_key = _natural_key(params, requested_time_str)
        lookup = snapshots_db.get_snapshot(pg_conn, natural_key)
        if lookup is None:
            raise ValueError(
                f"no ingested snapshot for {requested_time_str} -- run "
                "ingest_osm_building_snapshots for this instant first"
            )

        processed = object_store.get_json(s3_client, lookup.processed_object_uri)
        written = postgis.publish_snapshot_features(pg_conn, lookup.id, processed)
        return {
            "snapshot_id": lookup.id,
            "requested_time": requested_time_str,
            "features_written": written,
        }

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(minutes=15))
    def publish_changeset(pair: dict) -> dict:
        params = get_current_context().get("params", {})
        pg_conn = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).get_conn()
        s3_client = S3Hook(aws_conn_id=AWS_CONN_ID).get_conn()

        snap_a = snapshots_db.get_snapshot(pg_conn, _natural_key(params, pair["requested_time_a"]))
        snap_b = snapshots_db.get_snapshot(pg_conn, _natural_key(params, pair["requested_time_b"]))
        if snap_a is None or snap_b is None:
            raise ValueError(f"missing ingested snapshot(s) for pair {pair!r}")

        changeset = changesets_db.get_changeset(
            pg_conn,
            {
                "snapshot_a_id": snap_a.id,
                "snapshot_b_id": snap_b.id,
                "algorithm_version": params["algorithm_version"],
            },
        )
        if changeset is None:
            raise ValueError(
                f"no computed changeset for pair {pair!r} at algorithm_version="
                f"{params['algorithm_version']!r} -- run build_changesets first"
            )

        change_layer = object_store.get_json(s3_client, changeset.change_layer_object_uri)
        written = postgis.publish_change_features(
            pg_conn, changeset.id, snap_a.id, snap_b.id, change_layer
        )
        return {
            "changeset_id": changeset.id,
            "interval": f"{pair['requested_time_a']} -> {pair['requested_time_b']}",
            "change_records_written": written,
        }

    @task
    def summarize(snapshot_results: list[dict], changeset_results: list[dict]) -> None:
        for r in snapshot_results:
            log.info(
                "published snapshot_id=%s requested_time=%s features=%s",
                r["snapshot_id"], r["requested_time"], r["features_written"],
            )
        for r in changeset_results:
            log.info(
                "published changeset_id=%s interval=%s change_records=%s",
                r["changeset_id"], r["interval"], r["change_records_written"],
            )

    snapshot_results = publish_snapshot.expand(requested_time_str=get_requested_times())
    changeset_results = publish_changeset.expand(pair=get_comparison_pairs())
    # Structural ordering: change records join to published snapshot rows for
    # their before/after geometry, so every snapshot must land first.
    snapshot_results >> changeset_results
    # See ingest_osm_building_snapshots.py for why these need type: ignore --
    # they are XComArgs, not real lists, at DAG-definition time.
    summarize(snapshot_results, changeset_results)  # type: ignore[reportArgumentType]


publish_to_postgis()
