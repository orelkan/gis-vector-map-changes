"""DAG import/parsing and structure tests for publish_to_postgis."""

from __future__ import annotations

import pytest
from airflow.models import DagBag

DAG_ID = "publish_to_postgis"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder="dags")


def test_dag_bag_has_no_import_errors(dagbag: DagBag):
    assert dagbag.import_errors == {}


def test_dag_is_present_and_manually_triggered(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    assert dag.schedule is None
    assert dag.catchup is False


def test_dag_has_expected_tasks(dagbag: DagBag):
    task_ids = {t.task_id for t in dagbag.dags[DAG_ID].tasks}
    assert task_ids == {
        "get_requested_times", "get_comparison_pairs",
        "publish_snapshot", "publish_changeset", "summarize",
    }


def test_changesets_are_published_after_snapshots(dagbag: DagBag):
    # Not cosmetic: change records derive before/after geometry by joining to
    # already-published snapshot rows, so this ordering is a correctness
    # requirement, enforced structurally here and re-checked at runtime in
    # src/publish/postgis.py.
    dag = dagbag.dags[DAG_ID]
    assert "publish_snapshot" in dag.get_task("publish_changeset").upstream_task_ids


def test_publish_tasks_are_dynamically_mapped(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    for task_id in ("publish_snapshot", "publish_changeset"):
        assert "Mapped" in type(dag.get_task(task_id)).__name__


def test_defaults_cover_every_snapshot_and_changeset(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    assert len(dag.params["requested_times"]) == 7
    pairs = dag.params["comparison_pairs"]
    assert len(pairs) == 7
    # Both snapshots of every pair must themselves be published.
    times = set(dag.params["requested_times"])
    for pair in pairs:
        assert pair["requested_time_a"] in times
        assert pair["requested_time_b"] in times
