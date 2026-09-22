"""Tests for the Neo4j-backed vector store (fix #3).

Embeddings must land on the nodes in Neo4j so that every process sees them,
and search must ask the vector index rather than a per-process list.
"""

from app.db import vector_store
from app.db.vector_store import (
    EMBEDDING_DIMENSIONS,
    OVERSAMPLE_FACTOR,
    VECTOR_INDEX_NAME,
    count_indexed,
    create_vector_index,
    language_for_path,
    store_node_embeddings,
    vector_search,
)


class TestLanguageForPath:
    def test_typescript_is_not_reported_as_python(self):
        assert language_for_path("src/pages/GraphExplorer.tsx") == "typescript"
        assert language_for_path("src/api.ts") == "typescript"

    def test_python_and_javascript(self):
        assert language_for_path("app/main.py") == "python"
        assert language_for_path("public/sw.js") == "javascript"

    def test_unknown_extension(self):
        assert language_for_path("README.md") == "unknown"
        assert language_for_path("") == "unknown"


class TestCreateVectorIndex:
    def test_index_is_created_with_the_embedding_dimensions(self, fake_run_query):
        calls = fake_run_query()
        assert create_vector_index() is True

        query, params = calls[0]
        assert f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS" in query
        assert "FOR (n:Node) ON (n.embedding)" in query
        assert "'cosine'" in query
        assert params["dimensions"] == EMBEDDING_DIMENSIONS == 384

    def test_an_old_server_is_reported_rather_than_crashing(self, fake_run_query, monkeypatch):
        def boom(query, parameters=None):
            raise RuntimeError("Invalid input 'VECTOR'")

        monkeypatch.setattr(vector_store, "run_query", boom)
        assert create_vector_index() is False


class TestStoreNodeEmbeddings:
    def test_vectors_are_written_onto_the_matching_nodes(self, fake_run_query):
        calls = fake_run_query()
        rows = [{"id": "r:a.py:f", "embedding": [0.1, 0.2], "language": "python"}]

        assert store_node_embeddings(rows) == 1

        query, params = calls[0]
        assert "UNWIND $rows AS r" in query
        assert "MATCH (n:Node {id: r.id})" in query
        assert "db.create.setNodeVectorProperty(n, 'embedding', r.embedding)" in query
        assert params["rows"] == rows

    def test_writes_are_batched(self, fake_run_query, monkeypatch):
        calls = fake_run_query()
        monkeypatch.setattr(vector_store, "WRITE_BATCH_SIZE", 2)
        rows = [{"id": str(i), "embedding": [0.0]} for i in range(5)]

        assert store_node_embeddings(rows) == 5
        assert len(calls) == 3
        assert [len(params["rows"]) for _, params in calls] == [2, 2, 1]

    def test_no_query_is_run_for_an_empty_batch(self, fake_run_query):
        calls = fake_run_query()
        assert store_node_embeddings([]) == 0
        assert calls == []


class TestVectorSearch:
    ROW = {
        "node_id": "r:a.py:f",
        "name": "f",
        "type": "Function",
        "path": "a.py",
        "language": "python",
        "code": "def f(): pass",
        "summary": None,
        "similarity": 0.81,
    }

    def test_it_queries_the_vector_index(self, fake_run_query):
        calls = fake_run_query(lambda q, p: [self.ROW])

        results = vector_search([0.1] * 384, repo_id="r", top_k=5)

        query, params = calls[0]
        assert f"db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $vec)" in query
        assert params["repo_id"] == "r"
        assert params["top_k"] == 5
        assert results[0]["node_id"] == "r:a.py:f"
        assert results[0]["similarity"] == 0.81

    def test_it_oversamples_because_the_index_is_global(self, fake_run_query):
        """The repoId filter runs after the index lookup, so ask for more."""
        calls = fake_run_query()
        vector_search([0.1], repo_id="r", top_k=10)
        assert calls[0][1]["k"] == 10 * OVERSAMPLE_FACTOR

    def test_filters_are_passed_through(self, fake_run_query):
        calls = fake_run_query()
        vector_search([0.1], repo_id="r", top_k=3, similarity_threshold=0.5,
                      language="typescript", code_type="Function")
        params = calls[0][1]
        assert params["threshold"] == 0.5
        assert params["language"] == "typescript"
        assert params["code_type"] == "Function"

    def test_results_are_ordered_by_similarity_in_the_query(self, fake_run_query):
        calls = fake_run_query()
        vector_search([0.1], repo_id="r")
        assert "ORDER BY similarity DESC" in calls[0][0]


class TestCountIndexed:
    def test_counts_only_nodes_that_carry_an_embedding(self, fake_run_query):
        calls = fake_run_query(lambda q, p: [{"total": 42}])
        assert count_indexed("r") == 42
        assert "n.embedding IS NOT NULL" in calls[0][0]

    def test_a_failing_count_returns_zero_rather_than_raising(self, monkeypatch):
        def boom(query, parameters=None):
            raise RuntimeError("no database")

        monkeypatch.setattr(vector_store, "run_query", boom)
        assert count_indexed("r") == 0
