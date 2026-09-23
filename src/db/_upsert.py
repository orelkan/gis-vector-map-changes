"""The insert-if-absent-then-read-back pattern shared by every metadata
table in this project.

Each table's own module owns its SQL, its natural key and its row type --
those genuinely differ. What is identical, and worth having in exactly one
place, is the sequence: try to insert, and if the row already existed
(ON CONFLICT DO NOTHING returns nothing), read the existing one back, then
commit either way. That is what makes re-running a DAG task idempotent per
CLAUDE.md's versioning rules.
"""

from __future__ import annotations

from typing import Any


def upsert_returning(
    connection: Any,
    insert_sql: str,
    select_existing_sql: str,
    params: dict,
) -> tuple[tuple, bool]:
    """Execute `insert_sql`; fall back to `select_existing_sql` when the
    insert was a no-op. Returns (row, created).

    Both statements take the same `params` mapping and must return the same
    columns, in the same order, so the caller can build one row type from
    either outcome.
    """
    with connection.cursor() as cursor:
        cursor.execute(insert_sql, params)
        row = cursor.fetchone()
        created = row is not None
        if not created:
            cursor.execute(select_existing_sql, params)
            row = cursor.fetchone()
        connection.commit()
    return row, created
