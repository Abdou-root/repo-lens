import os
import logging
from typing import Optional, Dict, Any, List

try:
    from neo4j import GraphDatabase, basic_auth
except Exception:
    GraphDatabase = None

logger = logging.getLogger(__name__)

# Config via env vars
_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "test")

# Connection pooling config (performance optimization)
_NEO4J_MAX_CONNECTION_LIFETIME = int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "3600"))
_NEO4J_MAX_CONNECTION_POOL_SIZE = int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50"))
_NEO4J_CONNECTION_ACQUISITION_TIMEOUT = int(os.getenv("NEO4J_CONNECTION_ACQUISITION_TIMEOUT", "60"))

_driver = None
_schema_initialized = False


def get_driver():
    """
    Return a singleton Neo4j driver with optimized connection pooling.
    If neo4j driver is not installed, raises RuntimeError.
    """
    global _driver
    if GraphDatabase is None:
        raise RuntimeError("neo4j driver not installed. Install neo4j-driver to use Neo4j features.")
    if _driver is None:
        logger.info("Initializing Neo4j driver with connection pooling...")
        _driver = GraphDatabase.driver(
            _NEO4J_URI,
            auth=basic_auth(_NEO4J_USER, _NEO4J_PASSWORD),
            max_connection_lifetime=_NEO4J_MAX_CONNECTION_LIFETIME,
            max_connection_pool_size=_NEO4J_MAX_CONNECTION_POOL_SIZE,
            connection_acquisition_timeout=_NEO4J_CONNECTION_ACQUISITION_TIMEOUT,
        )
        logger.info(f"Neo4j driver initialized (pool_size={_NEO4J_MAX_CONNECTION_POOL_SIZE})")
    return _driver


def close_driver():
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        finally:
            _driver = None


def run_query(query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run a Cypher query and return list of record maps. Simple wrapper for PoC."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [record.data() for record in result]


def initialize_schema():
    """
    Initialize Neo4j database schema with constraints and indexes for optimal performance.

    Creates:
    - UNIQUE constraint on Node.id (enables fast lookups, prevents duplicates)
    - Index on Node.repoId (for filtering by repository)
    - Index on Node.type (for filtering by node type)
    - Index on RELATION.type (for filtering relationships)

    This dramatically improves edge persistence performance by enabling indexed lookups
    instead of full table scans. Expected improvement: ~10-20x faster node lookups.

    Note: Constraints and indexes are created with IF NOT EXISTS, making this idempotent.
    """
    global _schema_initialized

    if _schema_initialized:
        logger.debug("Schema already initialized, skipping")
        return

    driver = get_driver()

    schema_queries = [
        # Primary constraint on Node.id (most critical for performance)
        # This enables O(1) lookups instead of O(n) table scans
        "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE",

        # Index on repo_id for efficient repository filtering
        "CREATE INDEX node_repo_index IF NOT EXISTS FOR (n:Node) ON (n.repoId)",

        # Index on node type for type-based queries
        "CREATE INDEX node_type_index IF NOT EXISTS FOR (n:Node) ON (n.type)",

        # Index on relationship type for edge filtering
        "CREATE INDEX relation_type_index IF NOT EXISTS FOR ()-[r:RELATION]-() ON (r.type)",
    ]

    try:
        with driver.session() as session:
            for query in schema_queries:
                logger.info(f"Applying schema: {query[:60]}...")
                session.run(query)
                logger.info("✓ Schema applied successfully")

        _schema_initialized = True
        logger.info("Neo4j schema initialization complete - performance optimized!")

    except Exception as e:
        logger.error(f"Failed to initialize Neo4j schema: {e}")
        # Don't fail startup if schema creation fails
        # Indexes will be missing but queries will still work (just slower)
