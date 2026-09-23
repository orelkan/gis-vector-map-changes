"""Ingest dated Tel Aviv-Yafo building snapshots from OpenStreetMap (via the
ohsome API) and persist them durably (MinIO + Postgres metadata).

Orchestration only, per CLAUDE.md's architecture rules -- all business logic
lives in src/ingestion, src/storage, src/db, and is independently testable
without Airflow (see tests/). This DAG just wires: load AOI -> fetch ->
validate/normalize -> persist -> record.

Manually triggered (schedule=None): this DAG fetches specific historical
instants chosen for a monthly/yearly comparison MVP, not a recurring
"today's data" collection. A logical-date/backfill-driven design would be
the more idiomatic Airflow model for *ongoing* monthly collection, but
forcing that onto a fixed set of deliberately-chosen historical points now
would add catchup/start_date complexity without benefit -- see the plan
doc's DAG design section. Revisit this for a future continuous-monitoring
milestone.

Which instants get fetched comes from REQUESTED_TIMES in dags/common.py --
shared with publish_to_postgis so the two cannot disagree about what this
project holds. Dates end at 2026-07-01 (rather than the 2026-08-01
originally discussed) because ohsome's underlying data extent currently
reaches only 2026-07-27T09:00Z (confirmed via GET /v1/metadata); they were
shifted back one month, keeping the 1-month/1-year spacing, to stay inside
real data coverage.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Param, dag, task

from dags.common import (
    AWS_CONN_ID,
    DEFAULT_AOI_VERSION,
    DEFAULT_SOURCE_QUERY_VERSION,
    MINIO_BUCKET,
    POSTGRES_CONN_ID,
    REQUESTED_TIMES,
    current_params,
    parse_instant,
)
from src.db import snapshots as snapshots_db
from src.ingestion.aoi import load_aoi
from src.ingestion.snapshot import build_snapshot
from src.storage import object_store

log = logging.getLogger(__name__)


@dag(
    dag_id="ingest_osm_building_snapshots",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    tags=["ingestion", "osm", "buildings"],
    params={
        "requested_times": Param(
            REQUESTED_TIMES,
            type="array",
            description="ISO-8601 UTC instants (YYYY-MM-DDTHH:MM:SSZ) to fetch as independent snapshots.",
        ),
        "aoi_version": Param(DEFAULT_AOI_VERSION, type="string"),
        "source_query_version": Param(
            DEFAULT_SOURCE_QUERY_VERSION,
            type="string",
            description="Version of our extraction definition (ohsome filter + extracted tags + "
            "geometry normalization). Bump when that logic changes. "
            "v2: repair now keeps only polygonal parts, so snapshots are "
            "always Polygon/MultiPolygon (v1 could emit GeometryCollection).",
        ),
    },
)
def ingest_osm_building_snapshots():
    @task
    def get_requested_times() -> list[str]:
        return current_params()["requested_times"]

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        execution_timeout=timedelta(minutes=10),
    )
    def fetch_and_persist_snapshot(requested_time_str: str) -> dict:
        params = current_params()

        aoi = load_aoi()
        if aoi.aoi_version != params["aoi_version"]:
            raise ValueError(
                f"Requested aoi_version={params['aoi_version']!r} does not match "
                f"committed AOI file's aoi_version={aoi.aoi_version!r}"
            )

        requested_time = parse_instant(requested_time_str)

        result = build_snapshot(
            aoi, requested_time, source_query_version=params["source_query_version"]
        )

        s3_client = S3Hook(aws_conn_id=AWS_CONN_ID).get_conn()
        key_kwargs = {
            "source": result.source,
            "layer": result.layer,
            "aoi_id": result.aoi_id,
            "aoi_version": result.aoi_version,
            "requested_time_iso": requested_time_str,
        }
        raw_uri = object_store.put_json(
            s3_client,
            MINIO_BUCKET,
            object_store.snapshot_object_key(**key_kwargs, kind="raw"),
            result.raw_geojson,
        )
        processed_uri = object_store.put_json(
            s3_client,
            MINIO_BUCKET,
            object_store.snapshot_object_key(**key_kwargs, kind="processed"),
            result.processed_geojson,
        )

        pg_conn = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).get_conn()
        row = snapshots_db.upsert_snapshot(
            pg_conn,
            {
                "source": result.source,
                "source_query_version": result.source_query_version,
                "layer": result.layer,
                "aoi_id": result.aoi_id,
                "aoi_version": result.aoi_version,
                "requested_time": result.requested_time,
                "crs": result.crs,
                "raw_object_uri": raw_uri,
                "processed_object_uri": processed_uri,
                "feature_count": result.feature_count,
                "invalid_geometry_count": result.invalid_geometry_count,
                "repaired_geometry_count": result.repaired_geometry_count,
            },
        )

        return {
            "snapshot_id": row.id,
            "requested_time": requested_time_str,
            "feature_count": result.feature_count,
            "invalid_geometry_count": result.invalid_geometry_count,
            "repaired_geometry_count": result.repaired_geometry_count,
            "created": row.created,
        }

    @task
    def summarize(results: list[dict]) -> None:
        for r in results:
            log.info(
                "snapshot_id=%s requested_time=%s feature_count=%s "
                "invalid_geometry_count=%s repaired_geometry_count=%s created=%s",
                r["snapshot_id"],
                r["requested_time"],
                r["feature_count"],
                r["invalid_geometry_count"],
                r["repaired_geometry_count"],
                r["created"],
            )

    requested_times = get_requested_times()
    results = fetch_and_persist_snapshot.expand(requested_time_str=requested_times)
    # `results` is an XComArg (the mapped task's future output at runtime),
    # not a real list -- summarize()'s `list[dict]` annotation describes
    # what it receives once Airflow resolves it, which static analysis
    # can't see through. Inherent to TaskFlow cross-task typing.
    summarize(results)  # type: ignore[reportArgumentType]


ingest_osm_building_snapshots()
