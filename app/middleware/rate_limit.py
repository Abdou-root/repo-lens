"""
Rate limiting middleware using Redis for distributed enforcement.

This middleware enforces rate limits per-user and globally to prevent:
- DDoS attacks
- API abuse
- Resource exhaustion

Configuration via environment variables:
- RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: true)
- RATE_LIMIT_REQUESTS_PER_MINUTE: Global limit per IP (default: 60)
- RATE_LIMIT_REQUESTS_PER_MINUTE_AUTH: Limit for authenticated users (default: 120)
- RATE_LIMIT_BURST: Allow burst of requests (default: 10)
"""

import os
import time
import logging
from typing import Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from app.middleware.utils import should_skip_response_modification

logger = logging.getLogger(__name__)

# Configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
RATE_LIMIT_REQUESTS_PER_MINUTE_AUTH = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE_AUTH", "120"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "10"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Paths that should have stricter rate limits
STRICT_RATE_LIMIT_PATHS = [
    "/api/repos",           # Creating repos triggers expensive clone
    "/api/chat/stream",     # LLM calls are expensive
    "/api/llm/",            # All LLM endpoints
]

# Paths exempt from rate limiting
EXEMPT_PATHS = [
    "/health",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/favicon.ico",
    "/static/",
]


def get_redis_client():
    """Get Redis client for rate limiting."""
    try:
        from redis import Redis
        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning(f"Failed to connect to Redis for rate limiting: {e}")
        return None


def get_client_identifier(request: Request) -> str:
    """Get unique identifier for the client (user ID or IP)."""
    # Try to get user ID from auth header or cookie
    user_id = None

    # Check for user in request state (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        user_id = getattr(request.state.user, "id", None)

    if user_id:
        return f"user:{user_id}"

    # Fall back to IP address
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP if multiple proxies
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    return f"ip:{ip}"


def is_path_exempt(path: str) -> bool:
    """Check if path is exempt from rate limiting."""
    return any(path.startswith(exempt) for exempt in EXEMPT_PATHS)


def is_strict_path(path: str) -> bool:
    """Check if path should have stricter rate limits."""
    return any(path.startswith(strict) for strict in STRICT_RATE_LIMIT_PATHS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting middleware with sliding window algorithm.

    Uses a sliding window counter for accurate rate limiting across
    distributed systems.
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = RATE_LIMIT_REQUESTS_PER_MINUTE,
        requests_per_minute_auth: int = RATE_LIMIT_REQUESTS_PER_MINUTE_AUTH,
        burst: int = RATE_LIMIT_BURST,
        enabled: bool = RATE_LIMIT_ENABLED,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_minute_auth = requests_per_minute_auth
        self.burst = burst
        self.enabled = enabled
        self._redis = None
        self._last_redis_check = 0
        self._redis_check_interval = 30  # Re-check Redis every 30 seconds if failed

    def _get_redis(self):
        """Get Redis client with connection caching and retry."""
        now = time.time()

        # Return cached client if available
        if self._redis is not None:
            return self._redis

        # Only retry connection every N seconds
        if now - self._last_redis_check < self._redis_check_interval:
            return None

        self._last_redis_check = now
        self._redis = get_redis_client()
        return self._redis

    def _check_rate_limit(
        self,
        client_id: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """
        Check if client has exceeded rate limit using sliding window.

        Returns:
            (allowed, remaining, reset_seconds)
        """
        redis = self._get_redis()

        if redis is None:
            # If Redis unavailable, allow request (fail open)
            logger.debug("Redis unavailable, allowing request")
            return True, limit, 0

        now = time.time()
        window_start = now - window_seconds
        key = f"ratelimit:{client_id}"

        try:
            pipe = redis.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry on key
            pipe.expire(key, window_seconds * 2)

            results = pipe.execute()
            current_count = results[1]

            # Check if over limit (allow burst)
            effective_limit = limit + self.burst
            allowed = current_count < effective_limit
            remaining = max(0, effective_limit - current_count - 1)

            # Calculate reset time
            if not allowed:
                # Get oldest entry to determine when window resets
                oldest = redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_at = oldest[0][1] + window_seconds
                    reset_seconds = max(0, int(reset_at - now))
                else:
                    reset_seconds = window_seconds
            else:
                reset_seconds = window_seconds

            return allowed, remaining, reset_seconds

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            # Fail open on errors
            return True, limit, 0

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request with rate limiting."""

        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        if is_path_exempt(path):
            return await call_next(request)

        # Get client identifier
        client_id = get_client_identifier(request)
        is_authenticated = client_id.startswith("user:")

        # Determine rate limit based on path and auth status
        if is_strict_path(path):
            # Stricter limits for expensive operations
            limit = self.requests_per_minute // 3  # 1/3 of normal limit
        elif is_authenticated:
            limit = self.requests_per_minute_auth
        else:
            limit = self.requests_per_minute

        # Check rate limit
        allowed, remaining, reset_seconds = self._check_rate_limit(
            client_id=f"{client_id}:{path.split('/')[2] if len(path.split('/')) > 2 else 'root'}",
            limit=limit,
        )

        # Set rate limit headers
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_seconds),
        }

        if not allowed:
            logger.warning(f"Rate limit exceeded for {client_id} on {path}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": reset_seconds,
                },
                headers=headers,
            )

        # Process request and add headers to response
        response = await call_next(request)

        # Skip modifying streaming responses and redirects
        # Streaming responses: can't safely add headers after creation
        # Redirects: Firefox cross-origin compatibility
        if should_skip_response_modification(response):
            return response

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response


# In-memory fallback for when Redis is unavailable
class InMemoryRateLimiter:
    """Simple in-memory rate limiter as fallback."""

    def __init__(self, max_size: int = 10000):
        self._requests: dict[str, list[float]] = {}
        self._max_size = max_size

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        """Check rate limit. Returns (allowed, remaining)."""
        now = time.time()
        window_start = now - window

        # Cleanup old entries periodically
        if len(self._requests) > self._max_size:
            self._cleanup(window_start)

        # Get or create request list
        if key not in self._requests:
            self._requests[key] = []

        # Filter to current window
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        # Check limit
        current = len(self._requests[key])
        if current >= limit:
            return False, 0

        # Add current request
        self._requests[key].append(now)
        return True, limit - current - 1

    def _cleanup(self, cutoff: float):
        """Remove old entries."""
        keys_to_delete = []
        for key, times in self._requests.items():
            self._requests[key] = [t for t in times if t > cutoff]
            if not self._requests[key]:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._requests[key]
