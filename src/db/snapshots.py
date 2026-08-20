"""Metadata persistence for the `snapshots` table (see sql/001_create_snapshots.sql).

Takes an already-connected DBAPI connection (psycopg, or Airflow's
PostgresHook.get_conn() -- both expose the same cursor/commit interface)
rather than owning connection setup -- keeps this testable against a real
local Postgres without needing Airflow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple


class SnapshotRow(NamedTuple):
    id: int
    ingestion_time: datetime
    created: bool  # True if this call inserted a new row, False if it already existed


_UPSERT_SQL = """
    INSERT INTO snapshots (
        source, source_query_version, layer, aoi_id, aoi_version, requested_time,
        crs, raw_object_uri, processed_object_uri,
        feature_count, invalid_geometry_count, repaired_geometry_count
    )
    VALUES (%(source)s, %(source_query_version)s, %(layer)s, %(aoi_id)s, %(aoi_version)s,
            %(requested_time)s, %(crs)s, %(raw_object_uri)s, %(processed_object_uri)s,
            %(feature_count)s, %(invalid_geometry_count)s, %(repaired_geometry_count)s)
    ON CONFLICT ON CONSTRAINT snapshots_natural_key DO NOTHING
    RETURNING id, ingestion_time
"""

_SELECT_EXISTING_SQL = """
    SELECT id, ingestion_time FROM snapshots
    WHERE source = %(source)s AND source_query_version = %(source_query_version)s
      AND layer = %(layer)s AND aoi_id = %(aoi_id)s AND aoi_version = %(aoi_version)s
      AND requested_time = %(requested_time)s
"""


def upsert_snapshot(connection: Any, params: dict) -> SnapshotRow:
    """Insert a snapshot metadata row if one with the same natural key
    doesn't already exist. Idempotent: re-running with the same natural key
    returns the existing row instead of creating a duplicate, per
    CLAUDE.md's idempotency rules.

    `params` keys must match the SQL placeholders above: source,
    source_query_version, layer, aoi_id, aoi_version, requested_time, crs,
    raw_object_uri, processed_object_uri, feature_count,
    invalid_geometry_count, repaired_geometry_count.
    """
    with connection.cursor() as cursor:
        cursor.execute(_UPSERT_SQL, params)
        row = cursor.fetchone()
        if row is not None:
            connection.commit()
            return SnapshotRow(id=row[0], ingestion_time=row[1], created=True)

        cursor.execute(_SELECT_EXISTING_SQL, params)
        existing = cursor.fetchone()
        connection.commit()
        return SnapshotRow(id=existing[0], ingestion_time=existing[1], created=False)
