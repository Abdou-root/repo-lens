"""
Cost tracking and rate limiting for LLM usage.

This module provides application-wide cost tracking and limits to prevent
unexpected API bills. Features:
- Daily/monthly cost limits
- Per-user rate limiting
- Usage analytics
- Cost alerts
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CostLimit:
    """Cost limit configuration"""
    daily_limit: float = 10.0  # $10/day default
    monthly_limit: float = 100.0  # $100/month default
    per_user_daily_limit: float = 2.0  # $2/user/day default
    requests_per_minute: int = 30  # Rate limit


@dataclass
class UsageStats:
    """Usage statistics"""
    total_requests: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0
    start_time: datetime = field(default_factory=datetime.now)

    def get_summary(self) -> Dict[str, Any]:
        """Get usage summary"""
        runtime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
        cache_hit_rate = (self.cache_hits / max(self.total_requests, 1)) * 100

        return {
            "total_requests": self.total_requests,
            "total_cost": round(self.total_cost, 4),
            "total_tokens": self.total_tokens,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "errors": self.errors,
            "runtime_hours": round(runtime_hours, 2),
            "avg_cost_per_request": round(self.total_cost / max(self.total_requests, 1), 4),
            "requests_per_hour": round(self.total_requests / max(runtime_hours, 0.01), 2),
        }


class CostTracker:
    """
    Application-wide cost tracker and rate limiter.

    Tracks LLM usage across all users and enforces cost/rate limits.
    """

    def __init__(
        self,
        limits: Optional[CostLimit] = None,
        redis_client: Optional[Any] = None,
    ):
        """
        Initialize cost tracker.

        Args:
            limits: Cost limit configuration
            redis_client: Redis client for distributed tracking (optional)
        """
        self.limits = limits or CostLimit()
        self.redis_client = redis_client

        # In-memory tracking (use Redis in production for distributed systems)
        self.daily_stats = UsageStats()
        self.monthly_stats = UsageStats()
        self.user_stats = defaultdict(UsageStats)

        # Rate limiting
        self.request_timestamps = []  # List of recent request timestamps
        self.user_request_timestamps = defaultdict(list)

        # Last reset times
        self.last_daily_reset = datetime.now().date()
        self.last_monthly_reset = datetime.now().replace(day=1).date()

    def _reset_if_needed(self):
        """Reset counters if day/month has changed"""
        now = datetime.now()
        today = now.date()

        # Daily reset
        if today > self.last_daily_reset:
            self.daily_stats = UsageStats()
            self.user_stats.clear()
            self.last_daily_reset = today

        # Monthly reset
        first_of_month = now.replace(day=1).date()
        if first_of_month > self.last_monthly_reset:
            self.monthly_stats = UsageStats()
            self.last_monthly_reset = first_of_month

    def check_rate_limit(self, user_id: Optional[str] = None) -> bool:
        """
        Check if rate limit is exceeded.

        Args:
            user_id: Optional user ID for per-user rate limiting

        Returns:
            True if within rate limit, False if exceeded
        """
        now = time.time()
        cutoff = now - 60  # Last minute

        # Clean old timestamps
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > cutoff]

        # Check global rate limit
        if len(self.request_timestamps) >= self.limits.requests_per_minute:
            return False

        # Check per-user rate limit if user_id provided
        if user_id:
            user_timestamps = self.user_request_timestamps[user_id]
            user_timestamps = [ts for ts in user_timestamps if ts > cutoff]
            self.user_request_timestamps[user_id] = user_timestamps

            # User limit is half of global limit
            user_limit = self.limits.requests_per_minute // 2
            if len(user_timestamps) >= user_limit:
                return False

        return True

    def check_cost_limit(self, user_id: Optional[str] = None) -> Dict[str, bool]:
        """
        Check if cost limits are exceeded.

        Args:
            user_id: Optional user ID for per-user limits

        Returns:
            Dict with 'daily_ok', 'monthly_ok', 'user_daily_ok'
        """
        self._reset_if_needed()

        result = {
            "daily_ok": self.daily_stats.total_cost < self.limits.daily_limit,
            "monthly_ok": self.monthly_stats.total_cost < self.limits.monthly_limit,
            "user_daily_ok": True,
        }

        # Check per-user limit
        if user_id:
            user_cost = self.user_stats[user_id].total_cost
            result["user_daily_ok"] = user_cost < self.limits.per_user_daily_limit

        return result

    def can_make_request(self, user_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Check if a request can be made (rate + cost limits).

        Args:
            user_id: Optional user ID

        Returns:
            (allowed, reason) tuple. allowed=True if request can proceed.
        """
        # Check rate limit
        if not self.check_rate_limit(user_id):
            return False, "Rate limit exceeded. Please try again in a minute."

        # Check cost limits
        cost_check = self.check_cost_limit(user_id)

        if not cost_check["daily_ok"]:
            return False, f"Daily cost limit (${self.limits.daily_limit}) exceeded."

        if not cost_check["monthly_ok"]:
            return False, f"Monthly cost limit (${self.limits.monthly_limit}) exceeded."

        if not cost_check["user_daily_ok"]:
            return False, f"Your daily limit (${self.limits.per_user_daily_limit}) exceeded."

        return True, None

    def record_request(
        self,
        cost: float,
        tokens: int,
        cached: bool = False,
        user_id: Optional[str] = None,
        error: bool = False,
    ):
        """
        Record an LLM request.

        Args:
            cost: Cost of the request in dollars
            tokens: Total tokens used
            cached: Whether response was from cache
            user_id: Optional user ID
            error: Whether request resulted in error
        """
        self._reset_if_needed()

        now = time.time()

        # Record timestamp for rate limiting
        self.request_timestamps.append(now)
        if user_id:
            self.user_request_timestamps[user_id].append(now)

        # Update daily stats
        self.daily_stats.total_requests += 1
        self.daily_stats.total_cost += cost
        self.daily_stats.total_tokens += tokens
        if cached:
            self.daily_stats.cache_hits += 1
        else:
            self.daily_stats.cache_misses += 1
        if error:
            self.daily_stats.errors += 1

        # Update monthly stats
        self.monthly_stats.total_requests += 1
        self.monthly_stats.total_cost += cost
        self.monthly_stats.total_tokens += tokens
        if cached:
            self.monthly_stats.cache_hits += 1
        else:
            self.monthly_stats.cache_misses += 1
        if error:
            self.monthly_stats.errors += 1

        # Update user stats
        if user_id:
            user_stats = self.user_stats[user_id]
            user_stats.total_requests += 1
            user_stats.total_cost += cost
            user_stats.total_tokens += tokens
            if cached:
                user_stats.cache_hits += 1
            else:
                user_stats.cache_misses += 1
            if error:
                user_stats.errors += 1

    def get_stats(self, period: str = "daily") -> Dict[str, Any]:
        """
        Get usage statistics.

        Args:
            period: "daily" or "monthly"

        Returns:
            Usage statistics dict
        """
        self._reset_if_needed()

        if period == "monthly":
            stats = self.monthly_stats
        else:
            stats = self.daily_stats

        summary = stats.get_summary()

        # Add limit info
        summary["limits"] = {
            "daily_limit": self.limits.daily_limit,
            "monthly_limit": self.limits.monthly_limit,
            "per_user_daily_limit": self.limits.per_user_daily_limit,
            "requests_per_minute": self.limits.requests_per_minute,
        }

        # Add remaining budget
        if period == "monthly":
            summary["remaining_budget"] = round(self.limits.monthly_limit - stats.total_cost, 2)
        else:
            summary["remaining_budget"] = round(self.limits.daily_limit - stats.total_cost, 2)

        return summary

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a specific user"""
        self._reset_if_needed()

        user_stats = self.user_stats.get(user_id, UsageStats())
        summary = user_stats.get_summary()

        summary["user_id"] = user_id
        summary["daily_limit"] = self.limits.per_user_daily_limit
        summary["remaining_budget"] = round(
            self.limits.per_user_daily_limit - user_stats.total_cost, 2
        )

        return summary

    def reset_all(self):
        """Reset all statistics (use with caution)"""
        self.daily_stats = UsageStats()
        self.monthly_stats = UsageStats()
        self.user_stats.clear()
        self.request_timestamps.clear()
        self.user_request_timestamps.clear()


# Global cost tracker instance (can be configured via settings)
_global_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get global cost tracker instance"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker


def reset_cost_tracker():
    """Reset global cost tracker"""
    global _global_tracker
    _global_tracker = None
