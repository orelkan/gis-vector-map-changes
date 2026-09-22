"""Metadata persistence for the `changesets` table (see sql/002_create_changesets.sql).

Takes an already-connected DBAPI connection (psycopg, or Airflow's
PostgresHook.get_conn() -- both expose the same cursor/commit interface)
rather than owning connection setup -- keeps this testable against a real
local Postgres without needing Airflow. Mirrors src.db.snapshots exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple


class ChangesetRow(NamedTuple):
    id: int
    created_time: datetime
    created: bool  # True if this call inserted a new row, False if it already existed


class ChangesetLookup(NamedTuple):
    id: int
    change_layer_object_uri: str


_UPSERT_SQL = """
    INSERT INTO changesets (
        snapshot_a_id, snapshot_b_id, algorithm_version, change_layer_object_uri,
        unchanged_count, modified_geometry_count, modified_attributes_count,
        modified_geometry_and_attributes_count, added_count, removed_count, ambiguous_count
    )
    VALUES (%(snapshot_a_id)s, %(snapshot_b_id)s, %(algorithm_version)s, %(change_layer_object_uri)s,
            %(unchanged_count)s, %(modified_geometry_count)s, %(modified_attributes_count)s,
            %(modified_geometry_and_attributes_count)s, %(added_count)s, %(removed_count)s,
            %(ambiguous_count)s)
    ON CONFLICT ON CONSTRAINT changesets_natural_key DO NOTHING
    RETURNING id, created_time
"""

_SELECT_EXISTING_SQL = """
    SELECT id, created_time FROM changesets
    WHERE snapshot_a_id = %(snapshot_a_id)s AND snapshot_b_id = %(snapshot_b_id)s
      AND algorithm_version = %(algorithm_version)s
"""


def upsert_changeset(connection: Any, params: dict) -> ChangesetRow:
    """Insert a changeset metadata row if one with the same natural key
    doesn't already exist. Idempotent: re-running with the same natural key
    returns the existing row instead of creating a duplicate.

    `params` keys must match the SQL placeholders above: snapshot_a_id,
    snapshot_b_id, algorithm_version, change_layer_object_uri, and one
    *_count key per classification (see sql/002_create_changesets.sql).
    """
    with connection.cursor() as cursor:
        cursor.execute(_UPSERT_SQL, params)
        row = cursor.fetchone()
        if row is not None:
            connection.commit()
            return ChangesetRow(id=row[0], created_time=row[1], created=True)

        cursor.execute(_SELECT_EXISTING_SQL, params)
        existing = cursor.fetchone()
        connection.commit()
        return ChangesetRow(id=existing[0], created_time=existing[1], created=False)


_GET_SQL = """
    SELECT id, change_layer_object_uri FROM changesets
    WHERE snapshot_a_id = %(snapshot_a_id)s AND snapshot_b_id = %(snapshot_b_id)s
      AND algorithm_version = %(algorithm_version)s
"""


def get_changeset(connection: Any, params: dict) -> ChangesetLookup | None:
    """Look up an existing changeset by its natural key. Returns None if the
    comparison has not been computed -- callers that need it to exist (e.g.
    the publish DAG) should fail loudly rather than silently skip.

    `params` keys: snapshot_a_id, snapshot_b_id, algorithm_version.
    """
    with connection.cursor() as cursor:
        cursor.execute(_GET_SQL, params)
        row = cursor.fetchone()
    return ChangesetLookup(id=row[0], change_layer_object_uri=row[1]) if row else None
