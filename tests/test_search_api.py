"""Tests for the semantic search endpoint (fix #3, steps 4 and 5).

The endpoint must embed the query with the same model the worker used, ask
Neo4j's vector index, and return `node_id` at the top level of each result
(the frontend used to read `r.metadata.node_id`).
"""

import pytest

from app.api import search as search_api


class StubEmbedder:
    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.1] * 384

    def embed_code(self, code, language="python"):
        return [0.2] * 384

    def get_stats(self):
        return {"model_name": "all-MiniLM-L6-v2", "embedding_dimension": 384}


ROW = {
    "node_id": "repo1:app/auth/github.py:exchange_code",
    "name": "exchange_code",
    "type": "Function",
    "path": "app/auth/github.py",
    "language": "python",
    "code": "def exchange_code(): ...",
    "summary": "Exchanges an OAuth code for a token",
    "similarity": 0.72,
}


@pytest.fixture
def api(monkeypatch):
    """Stub the embedder and the vector store behind the endpoint."""
    embedder = StubEmbedder()
    calls = []

    def vector_search(**kwargs):
        calls.append(kwargs)
        return [dict(ROW)]

    monkeypatch.setattr(search_api, "vector_search", vector_search)
    monkeypatch.setattr(search_api, "count_indexed", lambda repo_id=None: 128)
    return embedder, calls


def run(coro):
    import asyncio
    return asyncio.run(coro)


class TestSemanticSearchEndpoint:
    def test_results_expose_node_id_at_the_top_level(self, api):
        embedder, _ = api
        request = search_api.SemanticSearchRequest(query="how is oauth handled", repo_id="repo1")

        response = run(search_api.semantic_search(request, embedder=embedder, current_user={}))

        assert response.count == 1
        result = response.results[0]
        assert result.node_id == "repo1:app/auth/github.py:exchange_code"
        assert result.similarity == 0.72
        assert result.language == "python"
        # metadata is kept for older clients
        assert result.metadata["node_id"] == result.node_id

    def test_the_query_is_embedded_and_the_filters_are_forwarded(self, api):
        embedder, calls = api
        request = search_api.SemanticSearchRequest(
            query="authentication logic",
            repo_id="repo1",
            language="python",
            code_type="function",
            top_k=7,
            similarity_threshold=0.4,
        )

        run(search_api.semantic_search(request, embedder=embedder, current_user={}))

        assert embedder.queries == ["authentication logic"]
        assert calls[0]["repo_id"] == "repo1"
        assert calls[0]["top_k"] == 7
        assert calls[0]["similarity_threshold"] == 0.4
        assert calls[0]["language"] == "python"
        assert calls[0]["code_type"] == "function"
        assert len(calls[0]["query_vector"]) == 384

    def test_total_indexed_comes_from_neo4j_not_an_in_process_list(self, api):
        embedder, _ = api
        request = search_api.SemanticSearchRequest(query="anything", repo_id="repo1")
        response = run(search_api.semantic_search(request, embedder=embedder, current_user={}))
        assert response.total_indexed == 128

    def test_a_search_failure_surfaces_as_a_500(self, monkeypatch):
        from fastapi import HTTPException

        def boom(**kwargs):
            raise RuntimeError("index missing")

        monkeypatch.setattr(search_api, "vector_search", boom)
        request = search_api.SemanticSearchRequest(query="x", repo_id="repo1")

        with pytest.raises(HTTPException) as excinfo:
            run(search_api.semantic_search(request, embedder=StubEmbedder(), current_user={}))

        assert excinfo.value.status_code == 500
