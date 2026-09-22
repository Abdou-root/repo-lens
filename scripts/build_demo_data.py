"""
Generate the static demo data the frontend serves when there is no backend.

Runs the real Tree-sitter parser over the three bundled demo repositories
(app/demo/repositories.py) and writes the resulting graphs, repository list
and insights as JSON under public/demo/. The frontend fetches those files
directly in demo mode, so a static deploy of the frontend alone gives a
working graph, node drawer, insights panel and name search.

Usage:
    python scripts/build_demo_data.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.demo.repositories import DEMO_REPOSITORIES  # noqa: E402
from app.services.insights import compute_insights  # noqa: E402
from app.services.parser import (  # noqa: E402
    _extract_python_nodes,
    _extract_ts_js_nodes,
    _resolve_calls,
    _resolve_imports,
)

OUTPUT_DIR = REPO_ROOT / "public" / "demo"

# The frontend's GraphNode type uses lowercase discriminators, while the
# parsers emit 'File' / 'Class' / 'Function'.
FRONTEND_TYPES = {"file": "file", "class": "class", "function": "function"}


def parse_repo(repo_id: str, repo: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Parse every file of a demo repo into graph nodes and edges."""
    nodes: List[Dict] = []
    edges: List[Dict] = []
    counter = 0

    for entry in repo.get("files", []):
        path = entry.get("path")
        code = entry.get("code")
        if not path or not code:
            continue

        ext = os.path.splitext(path)[1]
        extract = _extract_python_nodes if ext == ".py" else _extract_ts_js_nodes
        file_nodes, file_edges, counter = extract(code, path, repo_id, counter)

        nodes.extend(file_nodes)
        edges.extend(file_edges)

    nodes, edges = _resolve_imports(nodes, edges, repo_id)
    nodes, edges = _resolve_calls(nodes, edges, repo_id)

    return nodes, edges


def to_frontend_graph(nodes: List[Dict], edges: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Shape the parser output like the /api/graph/{repo_id} response.

    Node types are lowercased, and edges that point outside the repository
    are dropped: the frontend only renders edges between known nodes, and a
    dangling target would otherwise produce an invisible, unclickable edge.
    """
    out_nodes = []
    for node in nodes:
        node_type = FRONTEND_TYPES.get(str(node.get("type", "")).lower())
        if node_type is None:
            continue  # readme and anything else the graph does not render

        out_nodes.append({
            "id": node["id"],
            "type": node_type,
            "name": node.get("name", ""),
            "path": node.get("path", ""),
            "summary": node.get("docstring") or None,
            "code": node.get("code") or None,
            "lineCount": node.get("lineCount") or node.get("line_count"),
        })

    known_ids = {n["id"] for n in out_nodes}
    out_edges = [
        {
            "id": edge["id"],
            "source": edge["source"],
            "target": edge["target"],
            "type": edge["type"],
        }
        for edge in edges
        if edge["source"] in known_ids and edge["target"] in known_ids
    ]

    return {"nodes": out_nodes, "edges": out_edges}


def write_json(path: Path, payload: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return len(text)


def build(output_dir: Path = OUTPUT_DIR, verbose: bool = True) -> List[Dict[str, Any]]:
    """Write every demo artefact and return the repository index."""
    index = []

    for repo_id, repo in DEMO_REPOSITORIES.items():
        nodes, edges = parse_repo(repo_id, repo)
        graph = to_frontend_graph(nodes, edges)

        size = write_json(output_dir / "graph" / f"{repo_id}.json", graph)
        write_json(
            output_dir / "insights" / f"{repo_id}.json",
            compute_insights(repo_id, graph["nodes"], graph["edges"]),
        )

        file_count = len({n["path"] for n in graph["nodes"] if n["type"] == "file"})
        index.append({
            "id": repo_id,
            "name": repo.get("name", repo_id),
            "description": repo.get("description", ""),
            "language": repo.get("language", ""),
            "url": repo.get("url", ""),
            "stars": repo.get("stars", 0),
            "status": "complete",
            "nodeCount": len(graph["nodes"]),
            "edgeCount": len(graph["edges"]),
            "fileCount": file_count,
            "isDemo": True,
        })

        if verbose:
            edge_kinds = {}
            for edge in graph["edges"]:
                edge_kinds[edge["type"]] = edge_kinds.get(edge["type"], 0) + 1
            kinds = ", ".join(f"{n} {k}" for k, n in sorted(edge_kinds.items()))
            print(
                f"  {repo_id}: {len(graph['nodes'])} nodes, "
                f"{len(graph['edges'])} edges ({kinds}), {size / 1024:.1f} KB"
            )

    write_json(output_dir / "repositories.json", index)
    return index


if __name__ == "__main__":
    print(f"Building demo data into {OUTPUT_DIR.relative_to(REPO_ROOT)}/")
    repos = build()
    print(f"Wrote {len(repos)} repositories.")
