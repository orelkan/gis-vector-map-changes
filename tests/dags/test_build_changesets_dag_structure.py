"""DAG import/parsing and structure tests for build_changesets, per
CLAUDE.md's testing expectations. Mirrors test_dag_structure.py.
"""

from __future__ import annotations

import pytest
from airflow.models import DagBag

from dags.common import COMPARISON_PAIRS, REQUESTED_TIMES

DAG_ID = "build_changesets"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder="dags")


def test_dag_bag_has_no_import_errors(dagbag: DagBag):
    assert dagbag.import_errors == {}


def test_dag_is_present(dagbag: DagBag):
    assert DAG_ID in dagbag.dags


def test_dag_is_manually_triggered_not_scheduled(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    assert dag.schedule is None
    assert dag.catchup is False


def test_dag_has_expected_tasks(dagbag: DagBag):
    dag = dagbag.dags[DAG_ID]
    task_ids = {t.task_id for t in dag.tasks}
    assert task_ids == {"get_comparison_pairs", "build_and_persist_changeset", "summarize"}


def test_build_and_persist_changeset_is_dynamically_mapped(dagbag: DagBag):
    # One mapped task instance per comparison pair (monthly, yearly),
    # independently retryable -- not a single task looping internally.
    dag = dagbag.dags[DAG_ID]
    task = dag.get_task("build_and_persist_changeset")
    assert "Mapped" in type(task).__name__


def test_default_pairs_match_the_shared_comparison_inventory(dagbag: DagBag):
    # Shared with publish_to_postgis via dags/common.py: this DAG computes
    # the changesets that one publishes, so a pair present in only one of
    # them is either never computed or never served.
    dag = dagbag.dags[DAG_ID]
    pairs = dag.params["comparison_pairs"]

    assert pairs == COMPARISON_PAIRS
    # The monthly and yearly pairs docs/matching-spec.md pins expected counts
    # for are both present, alongside the 5-year span and the year-on-year
    # steps that make the per-building timeline continuous.
    assert {"requested_time_a": "2026-06-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"} in pairs
    assert {"requested_time_a": "2025-07-01T00:00:00Z", "requested_time_b": "2026-07-01T00:00:00Z"} in pairs
    assert all(p["requested_time_a"] in REQUESTED_TIMES for p in pairs)
    assert all(p["requested_time_b"] in REQUESTED_TIMES for p in pairs)


def test_default_source_query_version_matches_latest_ingestion_version(dagbag: DagBag):
    # Must track ingest_osm_building_snapshots's default -- otherwise this
    # DAG looks for snapshots that were never ingested under that version.
    dag = dagbag.dags[DAG_ID]
    assert dag.params["source_query_version"] == "v2"
