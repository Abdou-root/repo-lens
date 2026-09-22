"""
Vector storage and nearest-neighbour search backed by Neo4j.

Embeddings used to live in a Python list inside `SemanticSearch._code_index`.
The API and the RQ worker are separate processes (and RQ forks a child per
job), so the worker filled a list that the API never saw and that died with
the job. Everything already talks to Neo4j, so the vector lives on the node
and Neo4j's vector index does the nearest-neighbour search.

Requires Neo4j 5.15+ for the `CREATE VECTOR INDEX` syntax.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from app.db.neo4j_driver import run_query

logger = logging.getLogger(__name__)

# Name of the Neo4j vector index over (:Node).embedding
VECTOR_INDEX_NAME = "code_embeddings"

# all-MiniLM-L6-v2 produces 384-dimensional vectors
EMBEDDING_DIMENSIONS = 384

# Rows per UNWIND batch when writing vectors
WRITE_BATCH_SIZE = 200

# The vector index is global across every repository: it returns the k nearest
# nodes and only then is the repoId filter applied. Over-fetch so a small repo
# is not crowded out by a large one.
OVERSAMPLE_FACTOR = 10

# Map file extension -> language, so TypeScript code is not labelled "python"
LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}


def language_for_path(path: str) -> str:
    """Infer the language of a code element from its file extension."""
    return LANG_BY_EXT.get(os.path.splitext(path or "")[1], "unknown")


def create_vector_index() -> bool:
    """
    Create the vector index over (:Node).embedding if it does not exist.

    Returns True if the index exists after the call, False if the server is
    too old to support vector indexes (the app still works, without search).
    """
    query = (
        f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS\n"
        "FOR (n:Node) ON (n.embedding)\n"
        "OPTIONS {indexConfig: {\n"
        "  `vector.dimensions`: $dimensions,\n"
        "  `vector.similarity_function`: 'cosine'\n"
        "}}"
    )
    try:
        run_query(query, {"dimensions": EMBEDDING_DIMENSIONS})
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            return True
        logger.warning(
            "Could not create vector index %s (Neo4j 5.15+ required): %s",
            VECTOR_INDEX_NAME,
            e,
        )
        return False


def store_node_embeddings(rows: Sequence[Dict[str, Any]]) -> int:
    """
    Write embeddings onto existing (:Node) nodes.

    Args:
        rows: dicts with 'id', 'embedding' (list of floats) and optional
              'language'.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    query = (
        "UNWIND $rows AS r\n"
        "MATCH (n:Node {id: r.id})\n"
        "SET n.language = coalesce(r.language, n.language)\n"
        "WITH n, r\n"
        "CALL db.create.setNodeVectorProperty(n, 'embedding', r.embedding)\n"
    )

    written = 0
    for i in range(0, len(rows), WRITE_BATCH_SIZE):
        batch = list(rows[i:i + WRITE_BATCH_SIZE])
        run_query(query, {"rows": batch})
        written += len(batch)

    return written


def vector_search(
    query_vector: Sequence[float],
    repo_id: Optional[str] = None,
    top_k: int = 10,
    similarity_threshold: float = 0.0,
    language: Optional[str] = None,
    code_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find the nodes whose embedding is closest to `query_vector`.

    Filters (repo, language, type) are applied after the index lookup, so the
    index is asked for more candidates than the caller wants.

    Note on `similarity_threshold`: Neo4j normalises cosine similarity to
    (1 + cos) / 2, so unrelated vectors score around 0.5 and identical ones
    score 1.0 - not the raw [-1, 1] cosine the in-memory index returned.
    Thresholds below ~0.5 therefore filter nothing.
    """
    query = (
        f"CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $vec)\n"
        "YIELD node, score\n"
        "WHERE score >= $threshold\n"
        "  AND ($repo_id IS NULL OR node.repoId = $repo_id)\n"
        "  AND ($language IS NULL OR node.language = $language)\n"
        "  AND ($code_type IS NULL OR toLower(node.type) = toLower($code_type))\n"
        "RETURN node.id AS node_id, node.name AS name, node.type AS type,\n"
        "       node.path AS path, node.language AS language,\n"
        "       node.code AS code, node.summary AS summary, score AS similarity\n"
        "ORDER BY similarity DESC\n"
        "LIMIT $top_k"
    )

    records = run_query(query, {
        "vec": list(query_vector),
        "k": max(top_k * OVERSAMPLE_FACTOR, top_k),
        "top_k": top_k,
        "threshold": similarity_threshold,
        "repo_id": repo_id,
        "language": language,
        "code_type": code_type,
    })

    return [dict(r) for r in records]


def count_indexed(repo_id: Optional[str] = None) -> int:
    """Number of nodes that carry an embedding."""
    query = (
        "MATCH (n:Node)\n"
        "WHERE n.embedding IS NOT NULL\n"
        "  AND ($repo_id IS NULL OR n.repoId = $repo_id)\n"
        "RETURN count(n) AS total"
    )
    try:
        records = run_query(query, {"repo_id": repo_id})
        return int(records[0]["total"]) if records else 0
    except Exception as e:
        logger.warning("Failed to count indexed nodes: %s", e)
        return 0


def fetch_code_elements(
    repo_id: str,
    language: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    Fetch the functions and classes of a repository, with their source.

    Used by duplicate detection, which needs the code itself rather than a
    nearest-neighbour lookup.
    """
    query = (
        "MATCH (n:Node)\n"
        "WHERE n.repoId = $repo_id\n"
        "  AND toLower(n.type) IN ['function', 'class']\n"
        "  AND n.code IS NOT NULL AND n.code <> ''\n"
        "  AND ($language IS NULL OR n.language = $language)\n"
        "RETURN n.id AS node_id, n.name AS name, n.type AS type,\n"
        "       n.path AS path, n.language AS language, n.code AS code\n"
        "LIMIT $limit"
    )
    try:
        return [dict(r) for r in run_query(query, {
            "repo_id": repo_id,
            "language": language,
            "limit": limit,
        })]
    except Exception as e:
        logger.warning("Failed to fetch code elements for %s: %s", repo_id, e)
        return []
