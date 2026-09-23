"""Compare pairs of Tel Aviv-Yafo building snapshots and produce a
changeset (added/removed/modified_*/unchanged/ambiguous) for each pair,
persisted durably (MinIO change-layer GeoJSON + Postgres metadata).

Orchestration only, per CLAUDE.md's architecture rules -- the matching
algorithm lives in src/matching and is independently testable without
Airflow (see tests/matching/). This DAG just wires: fetch two snapshots ->
match -> render -> persist -> record. See docs/matching-spec.md for the
full specification this implements.

Manually triggered (schedule=None), for the same reason as
ingest_osm_building_snapshots: this compares specific, deliberately-chosen
snapshot pairs for the monthly/yearly MVP comparison, not a recurring
"latest vs previous" job. Revisit for a future continuous-monitoring
milestone.

Default comparison pairs come from dags/common.py, which is the single
inventory of what this project computes: the monthly (2026-06-01 ->
2026-07-01) and yearly (2025-07-01 -> 2026-07-01) pairs that
docs/matching-spec.md analyzes and pins expected counts for, plus the 5-year
span and the year-on-year steps the web UI's timeline needs. All against the
v2 snapshots (see ingest_osm_building_snapshots's v1->v2 note).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Param, dag, task

from dags.common import (
    AWS_CONN_ID,
    COMPARISON_PAIRS,
    DEFAULT_AOI_ID,
    DEFAULT_AOI_VERSION,
    DEFAULT_LAYER,
    DEFAULT_SOURCE,
    DEFAULT_SOURCE_QUERY_VERSION,
    MINIO_BUCKET,
    POSTGRES_CONN_ID,
    current_params,
    natural_key,
)
from src.db import changesets as changesets_db
from src.db import snapshots as snapshots_db
from src.ingestion.aoi import load_aoi
from src.matching.pipeline import SnapshotRef, build_changeset_result
from src.storage import object_store

log = logging.getLogger(__name__)


def _fetch_snapshot(pg_conn, s3_client, params: dict, requested_time_str: str):
    """Looks up a snapshot by natural key and fetches its processed GeoJSON.
    Fails loudly (rather than skip) if the snapshot doesn't exist --
    matching depends on ingestion having already run for this instant.
    """
    key = natural_key(params, requested_time_str)
    lookup = snapshots_db.get_snapshot(pg_conn, key)
    if lookup is None:
        raise ValueError(
            f"no ingested snapshot found for {key!r} -- run "
            "ingest_osm_building_snapshots for this instant first"
        )

    ref = SnapshotRef(id=lookup.id, **key)
    geojson = object_store.get_json(s3_client, lookup.processed_object_uri)
    return ref, geojson


@dag(
    dag_id="build_changesets",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    tags=["matching", "osm", "buildings"],
    params={
        "comparison_pairs": Param(
            COMPARISON_PAIRS,
            type="array",
            description="List of {requested_time_a, requested_time_b} ISO-8601 UTC instant "
            "pairs to compare. Both instants must already have an ingested snapshot.",
        ),
        "source": Param(DEFAULT_SOURCE, type="string"),
        "layer": Param(DEFAULT_LAYER, type="string"),
        "aoi_id": Param(DEFAULT_AOI_ID, type="string"),
        "aoi_version": Param(DEFAULT_AOI_VERSION, type="string"),
        "source_query_version": Param(
            DEFAULT_SOURCE_QUERY_VERSION,
            type="string",
            description="Which ingested snapshot version to compare -- must match an "
            "existing snapshots.source_query_version.",
        ),
    },
)
def build_changesets():
    @task
    def get_comparison_pairs() -> list[dict]:
        return current_params()["comparison_pairs"]

    @task(
        retries=3,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=15),
    )
    def build_and_persist_changeset(pair: dict) -> dict:
        params = current_params()

        pg_conn = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).get_conn()
        s3_client = S3Hook(aws_conn_id=AWS_CONN_ID).get_conn()

        snapshot_a, geojson_a = _fetch_snapshot(
            pg_conn, s3_client, params, pair["requested_time_a"]
        )
        snapshot_b, geojson_b = _fetch_snapshot(
            pg_conn, s3_client, params, pair["requested_time_b"]
        )

        aoi = load_aoi()
        if aoi.aoi_id != params["aoi_id"] or aoi.aoi_version != params["aoi_version"]:
            raise ValueError(
                f"requested aoi_id/aoi_version {params['aoi_id']!r}/{params['aoi_version']!r} "
                f"does not match committed AOI file's {aoi.aoi_id!r}/{aoi.aoi_version!r}"
            )

        result = build_changeset_result(
            snapshot_a, snapshot_b, geojson_a, geojson_b, aoi_geometry=aoi.geometry
        )

        change_layer_key = object_store.changeset_object_key(
            source=params["source"],
            layer=params["layer"],
            aoi_id=params["aoi_id"],
            aoi_version=params["aoi_version"],
            algorithm_version=result.algorithm_version,
            requested_time_a_iso=pair["requested_time_a"],
            requested_time_b_iso=pair["requested_time_b"],
        )
        change_layer_uri = object_store.put_json(
            s3_client, MINIO_BUCKET, change_layer_key, result.change_layer_geojson
        )

        row = changesets_db.upsert_changeset(
            pg_conn,
            {
                "snapshot_a_id": snapshot_a.id,
                "snapshot_b_id": snapshot_b.id,
                "algorithm_version": result.algorithm_version,
                "change_layer_object_uri": change_layer_uri,
                "unchanged_count": result.counts["unchanged"],
                "modified_geometry_count": result.counts["modified_geometry"],
                "modified_attributes_count": result.counts["modified_attributes"],
                "modified_geometry_and_attributes_count": result.counts[
                    "modified_geometry_and_attributes"
                ],
                "added_count": result.counts["added"],
                "removed_count": result.counts["removed"],
                "ambiguous_count": result.counts["ambiguous"],
            },
        )

        return {
            "changeset_id": row.id,
            "requested_time_a": pair["requested_time_a"],
            "requested_time_b": pair["requested_time_b"],
            "counts": result.counts,
            "created": row.created,
        }

    @task
    def summarize(results: list[dict]) -> None:
        for r in results:
            log.info(
                "changeset_id=%s %s -> %s counts=%s created=%s",
                r["changeset_id"],
                r["requested_time_a"],
                r["requested_time_b"],
                r["counts"],
                r["created"],
            )

    comparison_pairs = get_comparison_pairs()
    results = build_and_persist_changeset.expand(pair=comparison_pairs)
    # See ingest_osm_building_snapshots.py for why this needs a type: ignore
    # -- `results` is an XComArg, not a real list, at DAG-definition time.
    summarize(results)  # type: ignore[reportArgumentType]


build_changesets()
