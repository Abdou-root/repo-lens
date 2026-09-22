"""Tests for Q&A context retrieval (fixes #2 and #4).

#2: edges are stored as a single `:RELATION` type with the real kind in
    `r.type`, so `type(r)` labelled every neighbour "RELATION".
#4: retrieve by meaning (vector index), then expand one hop through the
    graph — the answer usually lives in the caller or the callee.
"""

import pytest

from app.services.llm.qa import CodeQA


class StubEmbedder:
    def embed_query(self, query):
        return [0.1] * 384


@pytest.fixture
def qa(fake_driver):
    """A CodeQA wired to a fake driver, with the LLM client stubbed out."""

    def build(rows_for=None):
        driver = fake_driver(rows_for)
        service = CodeQA.__new__(CodeQA)  # skip DeepSeekClient construction
        service.client = None
        service.neo4j_driver = driver
        service.embedder = StubEmbedder()
        return service, driver

    return build


def node_record(name, relations):
    return {
        "node": {"id": f"r:a.py:{name}", "name": name, "type": "Function",
                 "path": "a.py", "code": f"def {name}(): pass"},
        "n": {"id": f"r:a.py:{name}", "name": name, "type": "Function",
              "path": "a.py", "code": f"def {name}(): pass"},
        "score": 0.77,
        "relations": relations,
    }


class TestRelationLabels:
    def test_relations_use_the_type_property_not_the_neo4j_type(self, qa):
        """`type(r)` is always 'RELATION'; the real kind is r.type."""
        service, driver = qa(lambda q, p: [node_record("login", [
            {"relation": "calls", "target": "verify_password", "path": "auth.py"},
        ])])

        results = service.find_relevant_code("r", "how does login work?")

        assert "r.type" in driver.last_query
        assert "type(r)" not in driver.last_query
        assert results[0]["relations"][0]["relation"] == "calls"

    def test_the_hop_is_limited_so_a_hub_node_cannot_flood_the_prompt(self, qa):
        service, driver = qa(lambda q, p: [node_record("login", [])])
        service.find_relevant_code("r", "how does login work?")
        assert "[..8]" in driver.last_query or "[..10]" in driver.last_query

    def test_null_relations_from_an_optional_match_are_dropped(self, qa):
        """OPTIONAL MATCH yields one row of nulls for an unconnected node."""
        service, _ = qa(lambda q, p: [node_record("orphan", [
            {"relation": None, "target": None, "path": None},
        ])])
        results = service.find_relevant_code("r", "what is orphan?")
        assert results[0]["relations"] == []


class TestVectorRetrieval:
    def test_retrieval_goes_through_the_vector_index(self, qa):
        service, driver = qa(lambda q, p: [node_record("login", [])])

        results = service.find_relevant_code("r", "how is the user logged in?", max_results=5)

        query, params = driver.queries[0]
        assert "db.index.vector.queryNodes" in query
        assert params["repo_id"] == "r"
        assert len(params["qvec"]) == 384
        assert params["max_nodes"] == 5
        assert results[0]["relevance_score"] == 0.77

    def test_the_hop_only_follows_real_code_relationships(self, qa):
        service, driver = qa(lambda q, p: [node_record("login", [])])
        service.find_relevant_code("r", "how is the user logged in?")
        assert "OPTIONAL MATCH (node)-[r:RELATION]-(m:Node)" in driver.last_query
        assert "r.type IN ['calls', 'imports', 'defines']" in driver.last_query

    def test_a_question_with_no_matching_name_still_retrieves(self, qa):
        """The keyword retriever needed a function literally named 'login'."""
        service, _ = qa(lambda q, p: [node_record("authenticate_user", [])])
        results = service.find_relevant_code("r", "how is the user logged in?")
        assert [item["node"]["name"] for item in results] == ["authenticate_user"]


class TestKeywordFallback:
    def test_it_falls_back_when_no_node_has_an_embedding_yet(self, qa):
        def rows_for(query, params):
            if "db.index.vector.queryNodes" in query:
                return []  # nothing indexed
            return [node_record("login", [
                {"relation": "imports", "target": "jwt_handler", "path": "auth.py"},
            ])]

        service, driver = qa(rows_for)
        results = service.find_relevant_code("r", "explain login")

        assert "CONTAINS $keyword" in driver.last_query
        assert results[0]["node"]["name"] == "login"
        assert results[0]["relations"][0]["relation"] == "imports"

    def test_the_fallback_query_also_avoids_the_RELATION_label(self, qa):
        def rows_for(query, params):
            return [] if "queryNodes" in query else [node_record("login", [])]

        service, driver = qa(rows_for)
        service.find_relevant_code("r", "explain login")
        assert "type(r)" not in driver.last_query
        assert "[r:RELATION]" in driver.last_query

    def test_a_broken_vector_index_does_not_break_qa(self, qa):
        def rows_for(query, params):
            if "queryNodes" in query:
                raise RuntimeError("no such index: code_embeddings")
            return [node_record("login", [])]

        service, _ = qa(rows_for)
        results = service.find_relevant_code("r", "explain login")
        assert results[0]["node"]["name"] == "login"

    def test_no_driver_means_no_results_rather_than_an_error(self, qa):
        service, _ = qa()
        service.neo4j_driver = None
        assert service.find_relevant_code("r", "anything") == []


class TestContextFormatting:
    def test_relation_targets_render_as_names(self, qa):
        service, _ = qa()
        nodes = [{
            "node": {"name": "login", "type": "Function", "path": "auth.py", "code": "..."},
            "relations": [{"relation": "calls", "target": "verify_password"}],
            "relevance_score": 0.9,
        }]
        context = service.format_context_from_nodes(nodes, include_relations=True)
        assert "calls" in context
        assert "verify_password" in context
        assert "RELATION" not in context
