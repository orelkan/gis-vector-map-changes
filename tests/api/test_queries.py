"""SQL-shape tests for api/queries.py. No database needed -- these assert
how the query strings are built, which is where one class of silent failure
has been possible.
"""

from __future__ import annotations

from api import queries


def test_changeset_queries_are_composed_not_string_derived():
    # GET_CHANGESET was previously built by replacing LIST_CHANGESETS's
    # ORDER BY clause with a WHERE clause. If that replacement ever stopped
    # matching it would fail silently -- the query would return every
    # changeset and api.main._one would serve whichever came back first.
    assert "WHERE c.id = %(changeset_id)s" in queries.GET_CHANGESET
    assert "ORDER BY" not in queries.GET_CHANGESET
    assert "ORDER BY" in queries.LIST_CHANGESETS
    assert "WHERE" not in queries.LIST_CHANGESETS


def test_both_changeset_queries_select_the_same_columns():
    # api.main._changeset_payload reads the same keys from either query's
    # rows, so their select lists must not drift apart.
    def select_list(sql: str) -> str:
        return sql[sql.index("SELECT") : sql.index("FROM")]

    assert select_list(queries.LIST_CHANGESETS) == select_list(queries.GET_CHANGESET)
