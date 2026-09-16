"""Idempotency tests against a real local Postgres, per CLAUDE.md's rule to
test SQL against the actual local database rather than mocks. Mirrors
tests/db/test_snapshots.py.

Requires `make up && make migrate` to be running (localhost:5432).
Skipped automatically (see conftest.db_connection) if unreachable, and
excluded from the default `make test` run -- run explicitly with
`make test-db`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.db import changesets as changesets_db
from src.db import snapshots as snapshots_db

pytestmark = pytest.mark.db


def _snapshot_params(**overrides) -> dict:
    base = {
        "source": "test-source-changesets",
        "source_query_version": "v1",
        "layer": "building",
        "aoi_id": "test-aoi",
        "aoi_version": "v1",
        "requested_time": datetime(2026, 7, 1, tzinfo=UTC),
        "crs": "OGC:CRS84",
        "raw_object_uri": "s3://bucket/raw.geojson",
        "processed_object_uri": "s3://bucket/processed.geojson",
        "feature_count": 10,
        "invalid_geometry_count": 1,
        "repaired_geometry_count": 1,
    }
    base.update(overrides)
    return base


def _changeset_params(snapshot_a_id, snapshot_b_id, **overrides) -> dict:
    base = {
        "snapshot_a_id": snapshot_a_id,
        "snapshot_b_id": snapshot_b_id,
        "algorithm_version": "v1",
        "change_layer_object_uri": "s3://bucket/changesets/change_layer.geojson",
        "unchanged_count": 100,
        "modified_geometry_count": 2,
        "modified_attributes_count": 1,
        "modified_geometry_and_attributes_count": 0,
        "added_count": 3,
        "removed_count": 4,
        "ambiguous_count": 1,
    }
    base.update(overrides)
    return base


@pytest.fixture
def two_snapshots(db_connection):
    """Two real snapshot rows for changesets' foreign keys to reference."""
    a = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 6, 1, tzinfo=UTC))
    )
    b = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 7, 1, tzinfo=UTC))
    )
    yield a.id, b.id


@pytest.fixture(autouse=True)
def _cleanup_test_rows(db_connection):
    yield
    with db_connection.cursor() as cursor:
        # changesets first: its rows FK-reference snapshots.
        cursor.execute(
            """
            DELETE FROM changesets WHERE snapshot_a_id IN (
                SELECT id FROM snapshots WHERE source = %s
            ) OR snapshot_b_id IN (
                SELECT id FROM snapshots WHERE source = %s
            )
            """,
            ("test-source-changesets", "test-source-changesets"),
        )
        cursor.execute("DELETE FROM snapshots WHERE source = %s", ("test-source-changesets",))
    db_connection.commit()


def test_upsert_changeset_creates_new_row(db_connection, two_snapshots):
    a_id, b_id = two_snapshots

    row = changesets_db.upsert_changeset(db_connection, _changeset_params(a_id, b_id))

    assert row.created is True
    assert row.id is not None
    assert row.created_time is not None


def test_upsert_changeset_is_idempotent_for_same_natural_key(db_connection, two_snapshots):
    a_id, b_id = two_snapshots

    first = changesets_db.upsert_changeset(db_connection, _changeset_params(a_id, b_id))
    second = changesets_db.upsert_changeset(db_connection, _changeset_params(a_id, b_id))

    assert first.id == second.id
    assert first.created is True
    assert second.created is False

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM changesets WHERE id = %s", (first.id,))
        (count,) = cursor.fetchone()
    assert count == 1


def test_upsert_changeset_different_algorithm_version_creates_separate_row(
    db_connection, two_snapshots
):
    a_id, b_id = two_snapshots

    first = changesets_db.upsert_changeset(db_connection, _changeset_params(a_id, b_id))
    second = changesets_db.upsert_changeset(
        db_connection, _changeset_params(a_id, b_id, algorithm_version="v2")
    )

    assert first.id != second.id


def test_upsert_changeset_stores_classification_counts(db_connection, two_snapshots):
    a_id, b_id = two_snapshots

    row = changesets_db.upsert_changeset(
        db_connection,
        _changeset_params(a_id, b_id, unchanged_count=26944, modified_geometry_count=30),
    )

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT unchanged_count, modified_geometry_count FROM changesets WHERE id = %s",
            (row.id,),
        )
        unchanged, modified_geometry = cursor.fetchone()
    assert unchanged == 26944
    assert modified_geometry == 30
