"""Idempotency tests against a real local Postgres, per CLAUDE.md's rule to
test SQL against the actual local database rather than mocks.

Requires `make up && make migrate` to be running (localhost:5432).
Skipped automatically (see conftest.db_connection) if unreachable, and
excluded from the default `make test` run (see pyproject.toml addopts) --
run explicitly with `make test-db`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.db import snapshots as snapshots_db

pytestmark = pytest.mark.db


def _params(**overrides) -> dict:
    base = {
        "source": "test-source",
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


@pytest.fixture(autouse=True)
def _cleanup_test_rows(db_connection):
    yield
    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM snapshots WHERE source = %s", ("test-source",))
    db_connection.commit()


def test_upsert_snapshot_creates_new_row(db_connection):
    row = snapshots_db.upsert_snapshot(db_connection, _params())

    assert row.created is True
    assert row.id is not None
    assert row.ingestion_time is not None


def test_upsert_snapshot_is_idempotent_for_same_natural_key(db_connection):
    first = snapshots_db.upsert_snapshot(db_connection, _params())
    second = snapshots_db.upsert_snapshot(db_connection, _params())

    assert first.id == second.id
    assert first.created is True
    assert second.created is False

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM snapshots WHERE source = %s", ("test-source",))
        (count,) = cursor.fetchone()
    assert count == 1


def test_upsert_snapshot_different_requested_time_creates_separate_row(db_connection):
    first = snapshots_db.upsert_snapshot(db_connection, _params())
    second = snapshots_db.upsert_snapshot(
        db_connection,
        _params(requested_time=datetime(2026, 8, 1, tzinfo=UTC)),
    )

    assert first.id != second.id


def test_upsert_snapshot_different_aoi_version_creates_separate_row(db_connection):
    first = snapshots_db.upsert_snapshot(db_connection, _params())
    second = snapshots_db.upsert_snapshot(db_connection, _params(aoi_version="v2"))

    assert first.id != second.id
