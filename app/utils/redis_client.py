"""
Centralized Redis client management.

Provides a singleton Redis client to avoid repeated connection creation
across the application. Thread-safe with connection pooling.
"""

import os
import logging
import threading
from typing import Optional
from redis import Redis, ConnectionPool

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Thread-safe singleton
_lock = threading.Lock()
_connection_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None
_redis_client_decoded: Optional[Redis] = None


def get_connection_pool() -> ConnectionPool:
    """Get or create the Redis connection pool (thread-safe singleton)."""
    global _connection_pool
    if _connection_pool is None:
        with _lock:
            if _connection_pool is None:
                _connection_pool = ConnectionPool.from_url(REDIS_URL)
                logger.debug(f"Created Redis connection pool for {REDIS_URL}")
    return _connection_pool


def get_redis_client(decode_responses: bool = False) -> Redis:
    """
    Get or create a Redis client singleton.

    Args:
        decode_responses: If True, return strings instead of bytes.
                         Default False for binary compatibility.

    Returns:
        Redis client instance

    Note:
        This returns a shared client instance. For cases requiring
        isolated connections (like pubsub), create a new Redis instance.
    """
    global _redis_client, _redis_client_decoded

    if decode_responses:
        if _redis_client_decoded is None:
            with _lock:
                if _redis_client_decoded is None:
                    _redis_client_decoded = Redis.from_url(
                        REDIS_URL,
                        decode_responses=True
                    )
                    logger.debug("Created Redis client (decode_responses=True)")
        return _redis_client_decoded
    else:
        if _redis_client is None:
            with _lock:
                if _redis_client is None:
                    _redis_client = Redis.from_url(REDIS_URL)
                    logger.debug("Created Redis client (decode_responses=False)")
        return _redis_client


def get_redis_url() -> str:
    """Get the configured Redis URL."""
    return REDIS_URL


def create_redis_client(decode_responses: bool = False) -> Redis:
    """
    Create a new Redis client instance.

    Use this when you need an independent connection (e.g., for pubsub
    or blocking operations that shouldn't share the connection pool).

    Args:
        decode_responses: If True, return strings instead of bytes.

    Returns:
        New Redis client instance
    """
    return Redis.from_url(REDIS_URL, decode_responses=decode_responses)


def check_redis_connection() -> bool:
    """
    Check if Redis is reachable.

    Returns:
        True if Redis responds to ping, False otherwise
    """
    try:
        client = get_redis_client()
        return client.ping()
    except Exception as e:
        logger.warning(f"Redis connection check failed: {e}")
        return False
