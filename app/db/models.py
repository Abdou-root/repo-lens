import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db.neo4j_driver import run_query

logger = logging.getLogger(__name__)


def ensure_indexes():
    """
    Create necessary database indexes for optimal query performance.

    Should be called once at application startup.
    """
    indexes = [
        # Primary index for filtering nodes by repository
        ("CREATE INDEX node_repo_id IF NOT EXISTS FOR (n:Node) ON (n.repoId)", "node_repo_id"),
        # Index for node ID lookups
        ("CREATE INDEX node_id IF NOT EXISTS FOR (n:Node) ON (n.id)", "node_id"),
        # Index for repository lookups
        ("CREATE INDEX repo_id IF NOT EXISTS FOR (r:Repository) ON (r.id)", "repo_id"),
        # Index for user lookups by GitHub ID
        ("CREATE INDEX user_github_id IF NOT EXISTS FOR (u:User) ON (u.github_id)", "user_github_id"),
        # Index for edge types (for relationship queries)
        ("CREATE INDEX edge_type IF NOT EXISTS FOR (e:Edge) ON (e.type)", "edge_type"),
        # Composite index for node type + repo (for filtered queries)
        ("CREATE INDEX node_type_repo IF NOT EXISTS FOR (n:Node) ON (n.type, n.repoId)", "node_type_repo"),
    ]

    created = []
    failed = []

    for query, name in indexes:
        try:
            run_query(query, {})
            created.append(name)
        except Exception as e:
            # Index might already exist or syntax might differ by Neo4j version
            if "already exists" not in str(e).lower():
                logger.warning(f"Failed to create index {name}: {e}")
                failed.append(name)
            else:
                created.append(name)

    # Vector index for semantic search (Neo4j 5.15+). Created separately
    # because the syntax and the failure mode differ from plain indexes.
    from app.db.vector_store import VECTOR_INDEX_NAME, create_vector_index

    if create_vector_index():
        created.append(VECTOR_INDEX_NAME)
    else:
        failed.append(VECTOR_INDEX_NAME)

    if created:
        logger.info(f"Database indexes ensured: {', '.join(created)}")
    if failed:
        logger.warning(f"Failed to create indexes: {', '.join(failed)}")

    return len(failed) == 0


def _label_for_type(node_type: str) -> str:
    # Tree-sitter parsers emit capitalised types ('Function'), the legacy
    # fallback parsers emit lowercase ones ('function'): accept both.
    mapping = {
        "file": "File",
        "class": "Class",
        "function": "Function",
        "readme": "Readme",
    }
    return mapping.get(str(node_type or "").lower(), "File")


# Batch size for Neo4j operations to prevent timeout on large repos
BATCH_SIZE = 500


def create_nodes_and_edges(repo_id: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]):
    """Persist nodes and edges into Neo4j in batches. Uses MERGE to avoid duplicates.

    Nodes should include: id, type, name, path, summary?, code?, lineCount?
    Edges should include: id, source, target, type

    Uses batching to handle large repositories without timeout.
    """
    total_nodes = len(nodes)
    total_edges = len(edges)

    # Create nodes in batches
    if nodes:
        node_query = (
            "UNWIND $rows AS row\n"
            "MERGE (n:Node {id: row.id})\n"
            "SET n.name = row.name, n.path = row.path, n.type = row.type, "
            "n.summary = row.summary, n.code = row.code, n.content = row.content, "
            "n.lineCount = row.lineCount, n.repoId = row.repoId\n"
        )

        for i in range(0, total_nodes, BATCH_SIZE):
            batch = nodes[i:i + BATCH_SIZE]
            node_params = [{
                "id": n.get("id"),
                "name": n.get("name"),
                "path": n.get("path"),
                "type": n.get("type"),
                "summary": n.get("summary"),
                "code": n.get("code"),
                "content": n.get("content"),  # For README nodes
                "lineCount": n.get("lineCount"),
                "repoId": repo_id,
            } for n in batch]

            run_query(node_query, {"rows": node_params})
            logger.info(f"Persisted nodes {i + 1}-{i + len(batch)} of {total_nodes} for {repo_id}")

        # Add labels per type (this is quick, no batching needed)
        for t in set(n.get("type") for n in nodes):
            label = _label_for_type(t)
            q = (
                "MATCH (n:Node) WHERE n.type = $type AND n.repoId = $repoId SET n:`%s`" % label
            )
            run_query(q, {"type": t, "repoId": repo_id})

    # Create edges in batches
    if edges:
        edge_query = (
            "UNWIND $rows AS r\n"
            "MATCH (s:Node {id: r.source}), (t:Node {id: r.target})\n"
            "MERGE (s)-[rel:RELATION {id: r.id}]->(t)\n"
            "SET rel.type = r.type\n"
        )

        for i in range(0, total_edges, BATCH_SIZE):
            batch = edges[i:i + BATCH_SIZE]
            edge_params = [{
                "id": e.get("id"),
                "source": e.get("source"),
                "target": e.get("target"),
                "type": e.get("type"),
                "repoId": repo_id,
            } for e in batch]

            run_query(edge_query, {"rows": edge_params})
            logger.info(f"Persisted edges {i + 1}-{i + len(batch)} of {total_edges} for {repo_id}")


def get_graph_by_repo(repo_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Return nodes and edges for a repository."""
    try:
        q_nodes = (
            "MATCH (n:Node) WHERE n.repoId = $repoId RETURN n.id as id, n.type as type, n.name as name, n.path as path, n.summary as summary, n.lineCount as lineCount"
        )
        node_records = run_query(q_nodes, {"repoId": repo_id})
        
        nodes = []
        for record in node_records:
            nodes.append({
                "id": record.get("id"),
                "type": record.get("type"),
                "name": record.get("name"),
                "path": record.get("path"),
                "summary": record.get("summary"),
                "lineCount": record.get("lineCount"),
            })

        q_edges = (
            "MATCH (s:Node)-[r:RELATION]->(t:Node) WHERE s.repoId = $repoId RETURN r.id as id, s.id as source, t.id as target, r.type as type"
        )
        edge_records = run_query(q_edges, {"repoId": repo_id})
        edges = [
            {
                "id": record.get("id"),
                "source": record.get("source"),
                "target": record.get("target"),
                "type": record.get("type"),
            }
            for record in edge_records
        ]

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.error(f"Error retrieving graph for {repo_id}: {e}")
        return {"nodes": [], "edges": []}

def create_or_update_user(github_id: int, email: str, name: str, avatar_url: str) -> str:
    """Create or update user node in Neo4j. Returns user ID."""
    query = """
    MERGE (user:User {githubId: $github_id})
    ON CREATE SET 
        user.email = $email,
        user.name = $name,
        user.avatarUrl = $avatar_url,
        user.createdAt = datetime(),
        user.lastLogin = datetime()
    ON MATCH SET 
        user.lastLogin = datetime(),
        user.email = $email,
        user.name = $name,
        user.avatarUrl = $avatar_url
    RETURN user.githubId as github_id
    """
    result = run_query(query, {
        "github_id": github_id,
        "email": email,
        "name": name,
        "avatar_url": avatar_url,
    })
    return str(github_id) if result else None

def link_repo_to_user(repo_id: str, github_id: int) -> bool:
    """Link repository to user (user owns repo)"""
    query = """
    MATCH (user:User {githubId: $github_id}), (repo:Repository {repoId: $repo_id})
    MERGE (user)-[:OWNS]->(repo)
    RETURN true
    """
    result = run_query(query, {"github_id": github_id, "repo_id": repo_id})
    return bool(result)

def get_user_repos(github_id: int) -> list:
    """Get all repos owned by user with complete schema."""
    query = """
    MATCH (user:User {githubId: $github_id})-[:OWNS]->(repo:Repository)
    RETURN
        repo.repoId as id,
        repo.name as name,
        repo.url as url,
        repo.status as status,
        repo.nodeCount as nodeCount,
        repo.edgeCount as edgeCount,
        repo.fileCount as fileCount,
        repo.lastAnalyzed as lastAnalyzed,
        false as isDemo
    ORDER BY repo.createdAt DESC
    """
    result = run_query(query, {"github_id": github_id})

    # Ensure defaults for all repositories
    for repo in result:
        repo.setdefault('status', 'unknown')
        repo.setdefault('nodeCount', 0)
        repo.setdefault('edgeCount', 0)
        repo.setdefault('fileCount', 0)
        repo.setdefault('isDemo', False)

    return result


def create_repository(repo_id: str, url: str, name: str, github_id: int) -> bool:
    """Create Repository node in Neo4j and link to user."""
    query = """
    MATCH (user:User {githubId: $github_id})
    CREATE (repo:Repository {
        repoId: $repo_id,
        url: $url,
        name: $name,
        status: 'queued',
        createdAt: datetime(),
        nodeCount: 0,
        edgeCount: 0,
        fileCount: 0
    })
    CREATE (user)-[:OWNS]->(repo)
    RETURN repo.repoId as repoId
    """
    try:
        result = run_query(query, {
            "github_id": github_id,
            "repo_id": repo_id,
            "url": url,
            "name": name,
        })
        return bool(result)
    except Exception as e:
        logger.error(f"Failed to create repository {repo_id}: {e}")
        return False

def update_repository_status(repo_id: str, status: str, node_count: int = 0, edge_count: int = 0, file_count: int = 0) -> bool:
    """Update Repository node status and statistics."""
    query = """
    MATCH (repo:Repository {repoId: $repo_id})
    SET repo.status = $status,
        repo.nodeCount = $node_count,
        repo.edgeCount = $edge_count,
        repo.fileCount = $file_count,
        repo.lastAnalyzed = datetime()
    RETURN repo.repoId as repoId
    """
    try:
        result = run_query(query, {
            "repo_id": repo_id,
            "status": status,
            "node_count": node_count,
            "edge_count": edge_count,
            "file_count": file_count,
        })
        return bool(result)
    except Exception as e:
        logger.error(f"Failed to update repository status {repo_id}: {e}")
        return False


def update_task_status(
    repo_id: str,
    step: str,
    status: str,
    progress_pct: int,
    message: str,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Update task status in Neo4j for persistence across Redis disconnections.

    Args:
        repo_id: Repository ID
        step: Current step name (e.g., 'parsing', 'embedding', 'summarizing')
        status: Step status ('pending', 'in_progress', 'completed', 'failed')
        progress_pct: Progress percentage (0-100)
        message: Human-readable status message
        error: Error message if failed
        metadata: Additional metadata dict

    Returns:
        True if update successful
    """
    query = """
    MATCH (repo:Repository {repoId: $repo_id})
    SET repo.taskStep = $step,
        repo.taskStatus = $status,
        repo.taskProgress = $progress_pct,
        repo.taskMessage = $message,
        repo.taskError = $error,
        repo.taskMetadata = $metadata,
        repo.taskUpdatedAt = datetime()
    RETURN repo.repoId as repoId
    """
    try:
        # Serialize metadata to JSON string for Neo4j storage
        import json
        metadata_str = json.dumps(metadata) if metadata else None

        result = run_query(query, {
            "repo_id": repo_id,
            "step": step,
            "status": status,
            "progress_pct": progress_pct,
            "message": message,
            "error": error,
            "metadata": metadata_str,
        })
        return bool(result)
    except Exception as e:
        logger.error(f"Failed to update task status for {repo_id}: {e}")
        return False


def get_task_status(repo_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current task status from Neo4j.

    Args:
        repo_id: Repository ID

    Returns:
        Task status dict or None if not found
    """
    query = """
    MATCH (repo:Repository {repoId: $repo_id})
    RETURN
        repo.taskStep as step,
        repo.taskStatus as status,
        repo.taskProgress as progress_pct,
        repo.taskMessage as message,
        repo.taskError as error,
        repo.taskMetadata as metadata,
        repo.taskUpdatedAt as updated_at
    """
    try:
        result = run_query(query, {"repo_id": repo_id})
        if result and len(result) > 0:
            record = result[0]
            # Parse metadata from JSON string
            import json
            metadata = None
            if record.get("metadata"):
                try:
                    metadata = json.loads(record["metadata"])
                except json.JSONDecodeError:
                    metadata = None

            return {
                "step": record.get("step"),
                "status": record.get("status"),
                "progress_pct": record.get("progress_pct"),
                "message": record.get("message"),
                "error": record.get("error"),
                "metadata": metadata,
                "updated_at": record.get("updated_at"),
            }
        return None
    except Exception as e:
        logger.error(f"Failed to get task status for {repo_id}: {e}")
        return None


def clear_task_status(repo_id: str) -> bool:
    """
    Clear task status after completion or failure.

    Args:
        repo_id: Repository ID

    Returns:
        True if cleared successfully
    """
    query = """
    MATCH (repo:Repository {repoId: $repo_id})
    REMOVE repo.taskStep, repo.taskStatus, repo.taskProgress,
           repo.taskMessage, repo.taskError, repo.taskMetadata, repo.taskUpdatedAt
    RETURN repo.repoId as repoId
    """
    try:
        result = run_query(query, {"repo_id": repo_id})
        return bool(result)
    except Exception as e:
        logger.error(f"Failed to clear task status for {repo_id}: {e}")
        return False


def delete_repository(repo_id: str, github_id: int) -> bool:
    """
    Delete a repository and all its associated data from Neo4j.

    This performs a full deletion including:
    - The Repository node
    - All Node entities (files, classes, functions)
    - All RELATION edges between nodes
    - The OWNS relationship to the user

    Args:
        repo_id: Repository ID to delete
        github_id: GitHub ID of the user (for ownership verification)

    Returns:
        True if deletion was successful
    """
    # First verify ownership
    verify_query = """
    MATCH (user:User {githubId: $github_id})-[:OWNS]->(repo:Repository {repoId: $repo_id})
    RETURN repo.repoId as repoId
    """
    try:
        verify_result = run_query(verify_query, {"github_id": github_id, "repo_id": repo_id})
        if not verify_result:
            logger.warning(f"Repository {repo_id} not found or not owned by user {github_id}")
            return False

        # Delete all nodes associated with the repo
        delete_nodes_query = """
        MATCH (n:Node {repoId: $repo_id})
        DETACH DELETE n
        """
        run_query(delete_nodes_query, {"repo_id": repo_id})
        logger.info(f"Deleted all nodes for repository {repo_id}")

        # Delete the repository node and OWNS relationship
        delete_repo_query = """
        MATCH (user:User {githubId: $github_id})-[owns:OWNS]->(repo:Repository {repoId: $repo_id})
        DELETE owns, repo
        RETURN true
        """
        run_query(delete_repo_query, {"github_id": github_id, "repo_id": repo_id})
        logger.info(f"Deleted repository {repo_id} for user {github_id}")

        return True
    except Exception as e:
        logger.error(f"Failed to delete repository {repo_id}: {e}")
        return False