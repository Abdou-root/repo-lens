"""Shared test fixtures.

The Neo4j-facing code is tested against a fake driver that records the Cypher
it is given and returns canned rows, so the query shape and the result
mapping are covered without a live database.
"""

import pytest


class FakeResult(list):
    """A query result: a list of record dicts."""


class FakeSession:
    def __init__(self, recorder, rows_for):
        self._recorder = recorder
        self._rows_for = rows_for

    def run(self, query, parameters=None, **kwargs):
        params = dict(parameters or {})
        params.update(kwargs)
        self._recorder.append((query, params))
        return FakeResult(self._rows_for(query, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDriver:
    """Stands in for a neo4j.Driver."""

    def __init__(self, rows_for=None):
        self.queries = []
        self._rows_for = rows_for or (lambda q, p: [])

    def session(self):
        return FakeSession(self.queries, self._rows_for)

    @property
    def last_query(self):
        return self.queries[-1][0]

    @property
    def last_params(self):
        return self.queries[-1][1]


@pytest.fixture
def fake_driver():
    return FakeDriver


@pytest.fixture
def fake_run_query(monkeypatch):
    """Patch app.db.vector_store.run_query and record every call."""
    calls = []

    def install(rows_for=None):
        def run_query(query, parameters=None):
            calls.append((query, parameters or {}))
            return (rows_for or (lambda q, p: []))(query, parameters or {})

        monkeypatch.setattr("app.db.vector_store.run_query", run_query)
        return calls

    install.calls = calls
    return install
