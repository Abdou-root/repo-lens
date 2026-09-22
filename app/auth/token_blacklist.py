"""
Token Blacklist Management using Redis

This module provides functionality to blacklist JWT tokens on logout,
preventing token reuse even before expiration.
"""

import os
from typing import Optional
from redis import Redis
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TokenBlacklist:
    """Manages blacklisted JWT tokens in Redis"""

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize token blacklist.

        Args:
            redis_client: Optional Redis client. If not provided, creates one from REDIS_URL.
        """
        if redis_client is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.redis = Redis.from_url(redis_url, decode_responses=True)
        else:
            self.redis = redis_client

    def blacklist_token(self, jti: str, expires_at: datetime) -> bool:
        """
        Add a token to the blacklist.

        Args:
            jti: JWT ID (unique identifier for the token)
            expires_at: Token expiration timestamp

        Returns:
            True if successfully blacklisted, False otherwise
        """
        try:
            # Calculate TTL - how long until token naturally expires
            now = datetime.utcnow()
            if expires_at <= now:
                # Token already expired, no need to blacklist
                return True

            ttl_seconds = int((expires_at - now).total_seconds())

            # Store in Redis with TTL matching token expiration
            # After TTL expires, Redis automatically removes the entry
            key = f"blacklist:token:{jti}"
            self.redis.setex(key, ttl_seconds, "1")

            logger.info(f"Token {jti} blacklisted for {ttl_seconds} seconds")
            return True

        except Exception as e:
            logger.error(f"Failed to blacklist token {jti}: {e}")
            return False

    def is_blacklisted(self, jti: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            jti: JWT ID to check

        Returns:
            True if token is blacklisted, False otherwise
        """
        try:
            key = f"blacklist:token:{jti}"
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check blacklist for token {jti}: {e}")
            # Fail open - if Redis is down, allow the token
            # Token will still be rejected if expired by JWT verification
            return False

    def blacklist_all_user_tokens(self, user_id: str, ttl_seconds: int = 86400) -> bool:
        """
        Blacklist all tokens for a specific user.
        Useful for "logout everywhere" functionality.

        Args:
            user_id: User identifier (github_id)
            ttl_seconds: How long to keep the blacklist (default 24 hours)

        Returns:
            True if successfully blacklisted, False otherwise
        """
        try:
            key = f"blacklist:user:{user_id}"
            self.redis.setex(key, ttl_seconds, "1")
            logger.info(f"All tokens for user {user_id} blacklisted for {ttl_seconds} seconds")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist all tokens for user {user_id}: {e}")
            return False

    def is_user_blacklisted(self, user_id: str) -> bool:
        """
        Check if all tokens for a user are blacklisted.

        Args:
            user_id: User identifier to check

        Returns:
            True if user's tokens are blacklisted, False otherwise
        """
        try:
            key = f"blacklist:user:{user_id}"
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check user blacklist for {user_id}: {e}")
            return False

    def clear_user_blacklist(self, user_id: str) -> bool:
        """
        Clear user-level blacklist.

        Args:
            user_id: User identifier

        Returns:
            True if successfully cleared, False otherwise
        """
        try:
            key = f"blacklist:user:{user_id}"
            self.redis.delete(key)
            logger.info(f"User blacklist cleared for {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear user blacklist for {user_id}: {e}")
            return False


# Singleton instance
_blacklist_instance: Optional[TokenBlacklist] = None


def get_token_blacklist() -> TokenBlacklist:
    """Get or create the global token blacklist instance."""
    global _blacklist_instance
    if _blacklist_instance is None:
        _blacklist_instance = TokenBlacklist()
    return _blacklist_instance
