"""Shared wiring for this project's DAGs: connection names, the dated
snapshot/comparison inventory, and the few helpers all three repeat.

Not business logic -- that lives in src/ and is importable without Airflow
(CLAUDE.md's architecture rules). What is here is the Airflow-side glue that
was being written out three times: the same environment-backed connection
names, the same instant parsing, the same natural-key dict, and the same
`get_current_context()["params"]` idiom.

The dated inventory below is the single place that records which snapshots
and comparisons this project actually holds. It previously lived in each
DAG separately and had already drifted -- ingest_osm_building_snapshots
still defaulted to 3 of the 7 ingested instants, so triggering it on its
defaults silently covered under half the dataset.

Airflow parses this file, finds no DAG in it, and moves on.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from airflow.sdk import get_current_context

# Connection *names*, not credentials -- the actual secrets behind them live
# in Airflow's own encrypted Connection store, created from .env by
# airflow-init in docker-compose.yml (same env vars, so the two stay bound
# to the same names without hardcoding them twice).
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "gis-vector-map-changes")
AWS_CONN_ID = os.environ.get("MINIO_AIRFLOW_CONN_ID", "minio_default")
POSTGRES_CONN_ID = os.environ.get("GIS_POSTGRES_AIRFLOW_CONN_ID", "gis_postgres_default")

# Default identity of the data these DAGs operate on. Kept as plain values so
# each DAG can wrap them in its own Param() with its own description, without
# the defaults themselves drifting apart.
DEFAULT_SOURCE = "openstreetmap-ohsome"
DEFAULT_LAYER = "building"
DEFAULT_AOI_ID = "tel-aviv-yafo"
DEFAULT_AOI_VERSION = "v1"
DEFAULT_SOURCE_QUERY_VERSION = "v2"
DEFAULT_ALGORITHM_VERSION = "v1"

INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Every snapshot instant this project holds: annually from 2021-07-01 through
# 2025-07-01, plus 2026-06-01 and 2026-07-01, which together support the
# 1-month / 1-year / 5-year intervals the web UI offers. Dates stop at
# 2026-07 because ohsome's data extent currently reaches only
# 2026-07-27T09:00Z (confirmed via GET /v1/metadata).
REQUESTED_TIMES = [
    "2021-07-01T00:00:00Z",
    "2022-07-01T00:00:00Z",
    "2023-07-01T00:00:00Z",
    "2024-07-01T00:00:00Z",
    "2025-07-01T00:00:00Z",  # yearly baseline
    "2026-06-01T00:00:00Z",  # monthly baseline
    "2026-07-01T00:00:00Z",  # current (shared by several comparison pairs)
]

# Every comparison computed: the monthly and yearly pairs docs/matching-spec.md
# analyzes and pins expected counts for, the 5-year span, and the consecutive
# year-on-year steps that make the per-building timeline continuous.
COMPARISON_PAIRS = [
    {"requested_time_a": "2026-06-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2025-07-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2021-07-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"},
    {"requested_time_a": "2021-07-01T00:00:00Z", "requested_time_b": "2022-07-01T00:00:00Z"},
    {"requested_time_a": "2022-07-01T00:00:00Z", "requested_time_b": "2023-07-01T00:00:00Z"},
    {"requested_time_a": "2023-07-01T00:00:00Z", "requested_time_b": "2024-07-01T00:00:00Z"},
    {"requested_time_a": "2024-07-01T00:00:00Z", "requested_time_b": "2025-07-01T00:00:00Z"},
]


def parse_instant(iso: str) -> datetime:
    """Parse one of the ISO-8601 UTC instants above into an aware datetime."""
    return datetime.strptime(iso, INSTANT_FORMAT).replace(tzinfo=UTC)


def current_params() -> dict[str, Any]:
    """The running task's params.

    Airflow's Context TypedDict marks "params" as not required, even though
    it is always populated for a running task -- .get() with a default
    satisfies the type checker without changing behavior.
    """
    return get_current_context().get("params", {})


def natural_key(params: dict[str, Any], requested_time_str: str) -> dict[str, Any]:
    """The `snapshots` natural key for one instant, built from a task's
    params -- the lookup key src.db.snapshots expects.
    """
    return {
        "source": params["source"],
        "layer": params["layer"],
        "aoi_id": params["aoi_id"],
        "aoi_version": params["aoi_version"],
        "source_query_version": params["source_query_version"],
        "requested_time": parse_instant(requested_time_str),
    }
