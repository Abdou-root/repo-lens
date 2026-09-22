"""Tests for the static demo data served when only the frontend is hosted.

`scripts/build_demo_data.py` parses the bundled demo repositories with the
real parser and writes JSON into public/demo/. These tests check that the
committed files are well formed for the frontend and have not drifted from
what the current parser produces.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "public" / "demo"
FRONTEND_NODE_TYPES = {"file", "class", "function", "folder"}
FRONTEND_EDGE_TYPES = {"imports", "calls", "inherits", "external", "defines"}


def load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_demo_data", REPO_ROOT / "scripts" / "build_demo_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def index():
    return read(DEMO_DIR / "repositories.json")


def test_there_are_three_demo_repositories(index):
    assert [r["id"] for r in index] == [
        "demo_fastapi_backend",
        "demo_react_dashboard",
        "demo_ecommerce_api",
    ]


def test_ids_are_safe_to_use_as_file_names(index):
    """The frontend refuses ids that could escape public/demo/."""
    import re
    assert all(re.fullmatch(r"[\w-]+", r["id"]) for r in index)


@pytest.mark.parametrize("repo_id", [
    "demo_fastapi_backend", "demo_react_dashboard", "demo_ecommerce_api",
])
class TestEachGraph:
    def test_node_and_edge_types_match_the_frontend_types(self, repo_id):
        graph = read(DEMO_DIR / "graph" / f"{repo_id}.json")
        assert {n["type"] for n in graph["nodes"]} <= FRONTEND_NODE_TYPES
        assert {e["type"] for e in graph["edges"]} <= FRONTEND_EDGE_TYPES

    def test_every_edge_connects_two_known_nodes(self, repo_id):
        graph = read(DEMO_DIR / "graph" / f"{repo_id}.json")
        ids = {n["id"] for n in graph["nodes"]}
        assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])

    def test_ids_are_unique(self, repo_id):
        graph = read(DEMO_DIR / "graph" / f"{repo_id}.json")
        node_ids = [n["id"] for n in graph["nodes"]]
        edge_ids = [e["id"] for e in graph["edges"]]
        assert len(node_ids) == len(set(node_ids))
        assert len(edge_ids) == len(set(edge_ids))

    def test_index_counts_match_the_graph(self, repo_id, index):
        graph = read(DEMO_DIR / "graph" / f"{repo_id}.json")
        entry = next(r for r in index if r["id"] == repo_id)
        assert entry["nodeCount"] == len(graph["nodes"])
        assert entry["edgeCount"] == len(graph["edges"])

    def test_insights_exist_for_the_insights_panel(self, repo_id):
        insights = read(DEMO_DIR / "insights" / f"{repo_id}.json")
        assert insights["repo_id"] == repo_id
        assert set(insights["insights"]) == {
            "entry_points", "complexity_hotspots", "architecture_hubs", "isolated_modules",
        }


def test_the_python_demo_has_a_real_call_graph():
    """The old regex demo generator only ever produced 'defines' edges."""
    graph = read(DEMO_DIR / "graph" / "demo_fastapi_backend.json")
    kinds = {e["type"] for e in graph["edges"]}
    assert "calls" in kinds
    assert "imports" in kinds


def test_the_react_demo_resolves_its_relative_import():
    graph = read(DEMO_DIR / "graph" / "demo_react_dashboard.json")
    pairs = {(e["source"], e["target"]) for e in graph["edges"] if e["type"] == "imports"}
    assert (
        "demo_react_dashboard:src/components/Dashboard.tsx",
        "demo_react_dashboard:src/api/dashboard.ts",
    ) in pairs


def test_committed_files_match_a_fresh_build(tmp_path):
    """Fails if the parser changed and `python scripts/build_demo_data.py` was not rerun."""
    load_build_script().build(output_dir=tmp_path, verbose=False)

    fresh = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*.json"))
    committed = sorted(p.relative_to(DEMO_DIR) for p in DEMO_DIR.rglob("*.json"))
    assert fresh == committed

    for rel in fresh:
        assert read(tmp_path / rel) == read(DEMO_DIR / rel), (
            f"public/demo/{rel} is stale: run python scripts/build_demo_data.py"
        )
