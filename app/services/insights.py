"""
Structural insights derived from a code graph.

Pure graph analysis: no database and no LLM, so the same code serves the
live API endpoint and the static demo data generated at build time.
"""

from collections import defaultdict
from typing import Any, Dict, List

# A node needs at least this many connections to count as a hotspot
HOTSPOT_MIN_CONNECTIONS = 3

# Most entries returned per insight category
MAX_PER_CATEGORY = 5


def compute_insights(
    repo_id: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyse a graph and return its entry points, hotspots, hubs and leaves.

    Args:
        repo_id: Repository ID, echoed back in the response
        nodes: Graph nodes, each with at least 'id', 'name', 'type', 'path'
        edges: Graph edges, each with 'source', 'target' and 'type'

    Returns:
        The insights payload the frontend's InsightsPanel expects.
    """
    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    total_connections = defaultdict(int)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        # Skip folder edges
        if edge.get("type", "") == "contains":
            continue

        incoming[target] += 1
        outgoing[source] += 1
        total_connections[source] += 1
        total_connections[target] += 1

    # Filter to non-folder nodes
    code_nodes = [
        n for n in nodes
        if str(n.get("type", "")).lower() not in ("folder", "file")
    ]

    def describe(node, **extra):
        return {
            "id": node.get("id"),
            "name": node.get("name", "Unknown"),
            "type": node.get("type", "unknown"),
            "path": node.get("path", ""),
            **extra,
        }

    # 1. Entry Points (no incoming dependencies, but have outgoing)
    entry_points = []
    for node in code_nodes:
        node_id = node.get("id")
        if incoming[node_id] == 0 and outgoing[node_id] > 0:
            entry_points.append(describe(
                node,
                outgoing_calls=outgoing[node_id],
                reason=f"Entry point with {outgoing[node_id]} outgoing dependencies",
            ))

    # Sort by outgoing calls (most important entry points first)
    entry_points.sort(key=lambda x: x["outgoing_calls"], reverse=True)
    entry_points = entry_points[:MAX_PER_CATEGORY]

    # 2. Complexity Hotspots (highly connected nodes)
    hotspots = []
    for node in code_nodes:
        node_id = node.get("id")
        conn_count = total_connections[node_id]
        if conn_count >= HOTSPOT_MIN_CONNECTIONS:
            hotspots.append(describe(
                node,
                total_connections=conn_count,
                incoming=incoming[node_id],
                outgoing=outgoing[node_id],
                reason=(
                    f"{conn_count} total connections "
                    f"({incoming[node_id]} in, {outgoing[node_id]} out)"
                ),
            ))

    hotspots.sort(key=lambda x: x["total_connections"], reverse=True)
    hotspots = hotspots[:MAX_PER_CATEGORY]

    # 3. Architecture Hubs (many incoming, some outgoing - coordination points)
    hubs = []
    for node in code_nodes:
        node_id = node.get("id")
        inc = incoming[node_id]
        out = outgoing[node_id]
        if inc >= 2 and out >= 1:
            hubs.append(describe(
                node,
                incoming=inc,
                outgoing=out,
                reason=f"Central hub: {inc} callers, delegates to {out} functions",
            ))

    hubs.sort(key=lambda x: x["incoming"], reverse=True)
    hubs = hubs[:MAX_PER_CATEGORY]

    # 4. Isolated Modules (few external connections)
    isolated = []
    for node in code_nodes:
        node_id = node.get("id")
        conn_count = total_connections[node_id]
        if conn_count == 1:
            isolated.append(describe(
                node,
                connections=conn_count,
                reason="Weakly connected, may be leaf or isolated utility",
            ))

    isolated = isolated[:MAX_PER_CATEGORY]

    return {
        "repo_id": repo_id,
        "summary": {
            "total_nodes": len(nodes),
            "code_nodes": len(code_nodes),
            "total_edges": len(edges),
            "avg_connections": round(
                sum(total_connections.values()) / max(len(code_nodes), 1), 2
            ),
        },
        "insights": {
            "entry_points": entry_points,
            "complexity_hotspots": hotspots,
            "architecture_hubs": hubs,
            "isolated_modules": isolated,
        },
    }
