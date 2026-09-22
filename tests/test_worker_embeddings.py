"""Tests for the worker's embedding step (fix #3, step 3).

The worker used to fill an in-process list that died with the RQ job. It now
embeds in batches and writes the vectors onto the Neo4j nodes, so the API
process can search them.
"""

import pytest

from app.worker import tasks


class StubEmbedder:
    """Returns a deterministic 384-dim vector per text and records batches."""

    def __init__(self):
        self.batches = []

    def embed_batch(self, texts):
        self.batches.append(list(texts))
        return [[float(len(t))] * 384 for t in texts]


@pytest.fixture
def worker_env(monkeypatch):
    """Stub the embedder and capture what would be written to Neo4j."""
    embedder = StubEmbedder()
    stored = []

    monkeypatch.setattr(tasks, "get_embedder", lambda: embedder)
    monkeypatch.setattr(tasks, "store_node_embeddings", lambda rows: stored.extend(rows) or len(rows))
    monkeypatch.setattr(tasks, "publish_progress_detailed", lambda *a, **k: None)

    return embedder, stored


class Ctx:
    """Minimal stand-in for TaskContext."""

    def __init__(self):
        self.warnings = []


def node(node_id, node_type, name, path, code="pass"):
    return {"id": node_id, "type": node_type, "name": name, "path": path, "code": code}


class TestGenerateEmbeddings:
    def test_vectors_are_written_to_neo4j_for_functions_and_classes(self, worker_env):
        _, stored = worker_env
        nodes = [
            node("r:a.py", "File", "a.py", "a.py"),
            node("r:a.py:run", "Function", "run", "a.py"),
            node("r:a.py:Thing", "Class", "Thing", "a.py"),
        ]

        functions, classes = tasks._generate_embeddings_for_repo("r", nodes, Ctx())

        assert (functions, classes) == (1, 1)
        assert {row["id"] for row in stored} == {"r:a.py:run", "r:a.py:Thing"}
        assert all(len(row["embedding"]) == 384 for row in stored)

    def test_files_and_readmes_are_not_embedded(self, worker_env):
        _, stored = worker_env
        nodes = [
            node("r:a.py", "File", "a.py", "a.py"),
            node("r:README", "readme", "README", "README.md"),
        ]

        assert tasks._generate_embeddings_for_repo("r", nodes, Ctx()) == (0, 0)
        assert stored == []

    def test_language_comes_from_the_file_extension(self, worker_env):
        """TypeScript functions used to be stored as language='python'."""
        _, stored = worker_env
        nodes = [
            node("r:a.py:run", "Function", "run", "a.py"),
            node("r:b.tsx:Comp", "Function", "Comp", "src/b.tsx"),
            node("r:c.js:go", "Function", "go", "c.js"),
        ]

        tasks._generate_embeddings_for_repo("r", nodes, Ctx())

        languages = {row["id"]: row["language"] for row in stored}
        assert languages["r:a.py:run"] == "python"
        assert languages["r:b.tsx:Comp"] == "typescript"
        assert languages["r:c.js:go"] == "javascript"

    def test_embedding_happens_in_batches_not_one_call_per_node(self, worker_env, monkeypatch):
        embedder, stored = worker_env
        monkeypatch.setattr(tasks, "EMBED_BATCH_SIZE", 2)
        nodes = [node(f"r:a.py:f{i}", "Function", f"f{i}", "a.py") for i in range(5)]

        tasks._generate_embeddings_for_repo("r", nodes, Ctx())

        assert [len(b) for b in embedder.batches] == [2, 2, 1]
        assert len(stored) == 5

    def test_the_embedded_text_carries_name_summary_and_code(self, worker_env):
        embedder, _ = worker_env
        nodes = [{
            "id": "r:a.py:login", "type": "Function", "name": "login",
            "path": "a.py", "code": "def login(): ...", "summary": "Authenticates a user",
        }]

        tasks._generate_embeddings_for_repo("r", nodes, Ctx())

        text = embedder.batches[0][0]
        assert "login" in text
        assert "Authenticates a user" in text
        assert "def login(): ..." in text

    def test_a_failing_batch_is_recorded_and_the_rest_still_run(self, worker_env, monkeypatch):
        embedder, stored = worker_env
        monkeypatch.setattr(tasks, "EMBED_BATCH_SIZE", 1)

        calls = {"n": 0}
        original = embedder.embed_batch

        def flaky(texts):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("model OOM")
            return original(texts)

        monkeypatch.setattr(embedder, "embed_batch", flaky)
        nodes = [node(f"r:a.py:f{i}", "Function", f"f{i}", "a.py") for i in range(3)]

        ctx = Ctx()
        functions, _ = tasks._generate_embeddings_for_repo("r", nodes, ctx)

        assert functions == 2
        assert len(stored) == 2
        assert ctx.warnings

    def test_no_indexable_nodes_is_not_an_error(self, worker_env):
        assert tasks._generate_embeddings_for_repo("r", [], Ctx()) == (0, 0)
