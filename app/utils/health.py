"""
Health check utilities for RepoLens.

Provides comprehensive health checking for all system components:
- Neo4j connectivity and latency
- Redis connectivity and memory stats
- Embedding model availability
- RQ worker status
- Demo data loading status
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status values"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """
    Comprehensive health checker for all RepoLens components.

    Checks:
    - Neo4j database connectivity
    - Redis connectivity and memory
    - Embedding model availability
    - RQ worker status
    - Demo data status
    """

    def __init__(self):
        self._demo_data_status: Dict[str, Any] = {"status": "unknown"}

    def set_demo_data_status(self, status: str, details: Optional[Dict[str, Any]] = None):
        """Set demo data loading status (called from startup)"""
        self._demo_data_status = {
            "status": status,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    async def check_neo4j(self) -> ComponentHealth:
        """Check Neo4j connectivity and latency"""
        try:
            from app.db.neo4j_driver import get_driver

            start = time.time()
            driver = get_driver()
            driver.verify_connectivity()
            latency = (time.time() - start) * 1000

            # Get database info
            with driver.session() as session:
                result = session.run("CALL dbms.components() YIELD name, versions RETURN name, versions")
                db_info = result.single()

            return ComponentHealth(
                name="neo4j",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Connected",
                details={
                    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    "version": db_info["versions"][0] if db_info else "unknown"
                }
            )
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            return ComponentHealth(
                name="neo4j",
                status=HealthStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)[:100]}",
                details={"error": str(e)}
            )

    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity and memory stats"""
        try:
            from redis import Redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

            start = time.time()
            r = Redis.from_url(redis_url)
            r.ping()
            latency = (time.time() - start) * 1000

            # Get memory info
            info = r.info("memory")

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Connected",
                details={
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "connected_clients": r.info("clients").get("connected_clients", 0)
                }
            )
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)[:100]}",
                details={"error": str(e)}
            )

    async def check_embedding_model(self) -> ComponentHealth:
        """Check if embedding model is loaded and functional"""
        try:
            # Check if model is available via environment variable
            model_available = os.getenv("EMBEDDING_MODEL_AVAILABLE", "true").lower() == "true"

            if not model_available:
                return ComponentHealth(
                    name="embedding_model",
                    status=HealthStatus.DEGRADED,
                    message="Model not available (disabled)",
                    details={"reason": "EMBEDDING_MODEL_AVAILABLE=false"}
                )

            # Try to import and check model
            start = time.time()
            from app.services.embeddings import CodeEmbedder

            # Check if model is already loaded (singleton pattern)
            # This is a lightweight check - doesn't reload the model
            embedder = CodeEmbedder()
            dimension = embedder.get_embedding_dimension()
            latency = (time.time() - start) * 1000

            return ComponentHealth(
                name="embedding_model",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Model loaded",
                details={
                    "model_name": embedder.model_name,
                    "dimension": dimension,
                    "embeddings_generated": embedder.embeddings_generated
                }
            )
        except Exception as e:
            logger.warning(f"Embedding model health check failed: {e}")
            return ComponentHealth(
                name="embedding_model",
                status=HealthStatus.DEGRADED,
                message=f"Model check failed: {str(e)[:100]}",
                details={"error": str(e)}
            )

    async def check_worker(self) -> ComponentHealth:
        """Check RQ worker status"""
        try:
            from redis import Redis
            from rq import Queue
            from rq.worker import Worker

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

            start = time.time()
            redis_conn = Redis.from_url(redis_url)

            # Get workers
            workers = Worker.all(connection=redis_conn)
            worker_count = len(workers)

            # Get queue stats
            q = Queue(connection=redis_conn)
            queued_jobs = len(q)
            failed_jobs = len(q.failed_job_registry)

            latency = (time.time() - start) * 1000

            if worker_count == 0:
                return ComponentHealth(
                    name="worker",
                    status=HealthStatus.DEGRADED,
                    latency_ms=round(latency, 2),
                    message="No workers active",
                    details={
                        "worker_count": 0,
                        "queued_jobs": queued_jobs,
                        "failed_jobs": failed_jobs
                    }
                )

            return ComponentHealth(
                name="worker",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message=f"{worker_count} worker(s) active",
                details={
                    "worker_count": worker_count,
                    "queued_jobs": queued_jobs,
                    "failed_jobs": failed_jobs,
                    "workers": [w.name for w in workers[:5]]  # First 5 worker names
                }
            )
        except Exception as e:
            logger.warning(f"Worker health check failed: {e}")
            return ComponentHealth(
                name="worker",
                status=HealthStatus.UNHEALTHY,
                message=f"Worker check failed: {str(e)[:100]}",
                details={"error": str(e)}
            )

    async def check_demo_data(self) -> ComponentHealth:
        """Check demo data loading status"""
        status = self._demo_data_status.get("status", "unknown")
        details = self._demo_data_status.get("details", {})

        if status == "ready":
            return ComponentHealth(
                name="demo_data",
                status=HealthStatus.HEALTHY,
                message="Loaded",
                details=details
            )
        elif status == "skipped":
            return ComponentHealth(
                name="demo_data",
                status=HealthStatus.DEGRADED,
                message="Skipped",
                details=details
            )
        elif status == "failed":
            return ComponentHealth(
                name="demo_data",
                status=HealthStatus.UNHEALTHY,
                message="Failed to load",
                details=details
            )
        elif status == "loading":
            return ComponentHealth(
                name="demo_data",
                status=HealthStatus.DEGRADED,
                message="Loading in progress",
                details=details
            )
        else:
            return ComponentHealth(
                name="demo_data",
                status=HealthStatus.DEGRADED,
                message="Status unknown",
                details=details
            )

    async def get_detailed_health(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of all components.

        Returns dict with:
        - status: overall health status
        - timestamp: check timestamp
        - components: dict of component health details
        """
        # Run all checks
        neo4j_health = await self.check_neo4j()
        redis_health = await self.check_redis()
        embedding_health = await self.check_embedding_model()
        worker_health = await self.check_worker()
        demo_health = await self.check_demo_data()

        components = {
            "neo4j": self._component_to_dict(neo4j_health),
            "redis": self._component_to_dict(redis_health),
            "embedding_model": self._component_to_dict(embedding_health),
            "worker": self._component_to_dict(worker_health),
            "demo_data": self._component_to_dict(demo_health),
        }

        # Determine overall status
        all_statuses = [neo4j_health.status, redis_health.status, worker_health.status]

        if any(s == HealthStatus.UNHEALTHY for s in all_statuses):
            overall_status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in all_statuses):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": os.getenv("APP_VERSION", "dev"),
            "environment": os.getenv("APP_ENV", "development"),
            "components": components
        }

    async def is_ready(self) -> tuple[bool, Dict[str, Any]]:
        """
        Check if the service is ready to accept requests.

        Returns:
            Tuple of (is_ready, details)
        """
        # Critical components that must be healthy for readiness
        neo4j_health = await self.check_neo4j()
        redis_health = await self.check_redis()

        critical_healthy = (
            neo4j_health.status == HealthStatus.HEALTHY and
            redis_health.status == HealthStatus.HEALTHY
        )

        return critical_healthy, {
            "ready": critical_healthy,
            "neo4j": neo4j_health.status.value,
            "redis": redis_health.status.value,
        }

    def _component_to_dict(self, component: ComponentHealth) -> Dict[str, Any]:
        """Convert ComponentHealth to dict"""
        result = {
            "name": component.name,
            "status": component.status.value,
            "message": component.message,
        }
        if component.latency_ms is not None:
            result["latency_ms"] = component.latency_ms
        if component.details:
            result["details"] = component.details
        return result


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get global health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
