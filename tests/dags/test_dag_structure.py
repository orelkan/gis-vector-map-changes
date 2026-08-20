"""DAG import/parsing and structure tests, per CLAUDE.md's testing
expectations ("DAG import/parsing", "task dependency structure").
"""

from __future__ import annotations

import pytest
from airflow.models import DagBag

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


def test_default_params_define_three_requested_times(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    default_times = dag.params["requested_times"]
    assert len(default_times) == 3
    # Spacing: one pair one month apart, one pair one year apart, sharing
    # the "current" instant -- see the plan doc / DAG docstring for why
    # these specific dates (shifted to stay inside ohsome's data extent).
    assert default_times == [
        "2025-07-01T00:00:00Z",
        "2026-06-01T00:00:00Z",
        "2026-07-01T00:00:00Z",
    ]
