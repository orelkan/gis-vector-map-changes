"""DAG import/parsing and structure tests, per CLAUDE.md's testing
expectations ("DAG import/parsing", "task dependency structure").
"""

from __future__ import annotations

import pytest
from airflow.models import DagBag

from dags.common import REQUESTED_TIMES

DAG_ID = "ingest_osm_building_snapshots"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder="dags")


def test_dag_bag_has_no_import_errors(dagbag: DagBag):
    assert dagbag.import_errors == {}


def test_dag_is_present(dagbag: DagBag):
    assert DAG_ID in dagbag.dags


def test_dag_is_manually_triggered_not_scheduled(dagbag: DagBag):
    # Deliberate: see the DAG's module docstring for why this fetches fixed
    # historical instants rather than running on a recurring schedule.
    dag = dagbag.dags[DAG_ID]
    assert dag.schedule is None
    assert dag.catchup is False


def test_dag_has_expected_tasks(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    task_ids = {t.task_id for t in dag.tasks}
    assert task_ids == {"get_requested_times", "fetch_and_persist_snapshot", "summarize"}


def test_fetch_and_persist_snapshot_is_dynamically_mapped(dagbag: DagBag):
    # Confirms the per-date fan-out is real dynamic task mapping (one
    # mapped task instance per requested_time, independently retryable),
    # not a single task looping internally.
    dag = dagbag.dags[DAG_ID]
    task = dag.get_task("fetch_and_persist_snapshot")
    assert "Mapped" in type(task).__name__


def test_default_requested_times_cover_every_held_snapshot(dagbag: DagBag):
    # These defaults used to list only 3 instants while 7 were actually
    # ingested and published, so triggering this DAG on its defaults covered
    # under half the dataset. Both the inventory and this assertion now come
    # from dags/common.py, so they cannot drift apart again.
    dag = dagbag.dags[DAG_ID]

    assert dag.params["requested_times"] == REQUESTED_TIMES
    # Annually 2021..2025, plus the two 2026 instants that give the web UI
    # its 1-month interval. Dates stop at 2026-07 because that is where
    # ohsome's data extent currently ends.
    assert dag.params["requested_times"] == [
        "2021-07-01T00:00:00Z",
        "2022-07-01T00:00:00Z",
        "2023-07-01T00:00:00Z",
        "2024-07-01T00:00:00Z",
        "2025-07-01T00:00:00Z",
        "2026-06-01T00:00:00Z",
        "2026-07-01T00:00:00Z",
    ]
