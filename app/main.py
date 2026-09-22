import asyncio
import json
import jwt
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Depends, status
import os
from fastapi.responses import StreamingResponse, RedirectResponse
from app.schemas import Repository, ChatRequest, ChatMessage, GraphResponse, GraphNode
from redis import Redis
from rq import Queue
from app.worker import tasks as worker_tasks
from app.utils.progress_pubsub import subscribe_progress

# Centralized logging - configure before other imports
from app.utils.logging_config import (
    configure_logging,
    get_logger,
    set_correlation_id,
    log_service_startup,
)

# Configure logging at module load
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name=os.getenv("SERVICE_NAME", "repolens-api")
)
logger = get_logger(__name__)

# Auth imports
from app.auth.github import get_github_auth_url, exchange_code_for_token, get_github_user
from app.auth.jwt_handler import create_token
from app.auth.dependencies import get_current_user, get_current_user_optional
from app.db.models import create_or_update_user, link_repo_to_user, get_user_repos, delete_repository

# Demo mode imports
from app.api import demo as demo_router
from app.demo import initialize_demo_data, get_demo_config

# Health check utilities
from app.utils.health import get_health_checker


def calculate_job_timeout(estimated_files: int = None) -> int:
    """
    Calculate job timeout based on estimated repository size.

    Args:
        estimated_files: Estimated number of files (if known)

    Returns:
        Timeout in seconds
    """
    if estimated_files is None:
        return 600  # Default 10 minutes if unknown

    if estimated_files <= 100:
        return 180   # 3 minutes for small repos
    elif estimated_files <= 500:
        return 360   # 6 minutes for medium repos
    elif estimated_files <= 1000:
        return 600   # 10 minutes for large repos
    else:
        return 1800  # 30 minutes for very large repos


# LLM and Search imports
from app.api import llm as llm_router
from app.api import search as search_router

# CORS
from fastapi.middleware.cors import CORSMiddleware

# Security middleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.csrf import CSRFProtectionMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

app = FastAPI(title="RepoLens - Backend PoC")

# Add security middleware FIRST (outermost layer)
is_production = os.getenv("APP_ENV", "development") == "production"

# Allow testing production security settings in development
# Set FORCE_SECURE_COOKIES=true to test secure cookie behavior locally
force_secure = os.getenv("FORCE_SECURE_COOKIES", "false").lower() == "true"
use_production_security = is_production or force_secure

# Frontend URL configuration (for OAuth redirects)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")

# 1. Security headers (CSP, XSS protection, etc.)
# Note: CSP connect-src needs actual production mode to restrict, not just force_secure
app.add_middleware(SecurityHeadersMiddleware, is_production=is_production)

# 1.5. Rate limiting (before other middleware to catch abuse early)
app.add_middleware(RateLimitMiddleware)

# 2. CSRF protection (exempt auth endpoints that use OAuth flow)
app.add_middleware(
    CSRFProtectionMiddleware,
    exempt_paths=[
        "/api/auth/github",
        "/api/auth/github/callback",
        "/api/auth/refresh",
        "/api/auth/logout",  # Already protected by auth dependency
        "/health",
        "/health/detailed",
        "/health/ready",
    ],
    is_production=use_production_security,  # Use force_secure flag for cookie testing
)

# 3. CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8080,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. GZip compression for large responses (improves performance)
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Include routers
app.include_router(demo_router.router)
app.include_router(llm_router.router)
app.include_router(search_router.router)

# In-memory stores for PoC
REPOS: Dict[str, Dict[str, Any]] = {}
GRAPHS: Dict[str, Dict[str, Any]] = {}


# Correlation ID middleware for request tracing
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to each request for tracing."""
    from fastapi.responses import JSONResponse
    from app.middleware.utils import should_skip_response_modification

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_correlation_id(request_id)

    try:
        response = await call_next(request)

        # Validate response exists
        if response is None:
            logger.error(f"No response returned for request {request_id}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"X-Request-ID": request_id}
            )

        # Skip header modification for streaming responses and redirects
        if should_skip_response_modification(response):
            # Still try to add correlation ID if possible (won't crash if fails)
            try:
                response.headers["X-Request-ID"] = request_id
            except Exception:
                pass  # StreamingResponse headers are read-only, skip silently
            return response

        # Safe to add header for regular responses
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        # Catch ANY exception from downstream middleware/handlers
        logger.exception(f"Unhandled exception in request {request_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id}
        )


def validate_production_secrets():
    """
    Validate that production secrets are properly configured.

    Raises warnings in development, errors in production if defaults are used.
    """
    issues = []
    warnings_list = []

    # Check JWT secret
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    default_secrets = [
        "your-secret-key-change-in-production",
        "change-me",
        "secret",
        "your-secret-key",
        "",
    ]
    if jwt_secret.lower() in [s.lower() for s in default_secrets] or len(jwt_secret) < 32:
        msg = "JWT_SECRET_KEY is not set or uses a default value. Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        if is_production:
            issues.append(msg)
        else:
            warnings_list.append(msg)

    # Check database password
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    if "u9H471XseDuRKZ3Mv6d9" in neo4j_password:  # Part of default password
        msg = "NEO4J_PASSWORD appears to be using the default example password"
        if is_production:
            issues.append(msg)
        else:
            warnings_list.append(msg)

    # Check for HTTPS in production
    if is_production:
        force_https = os.getenv("FORCE_HTTPS", "false").lower() == "true"
        if not force_https:
            warnings_list.append("FORCE_HTTPS is not enabled in production")

        secure_cookies = os.getenv("SECURE_COOKIES", "false").lower() == "true"
        if not secure_cookies:
            warnings_list.append("SECURE_COOKIES is not enabled in production")

    # Check CORS origins
    cors_origins = os.getenv("CORS_ORIGINS", "")
    if "*" in cors_origins:
        msg = "CORS_ORIGINS contains wildcard '*' which is insecure"
        if is_production:
            issues.append(msg)
        else:
            warnings_list.append(msg)

    # Log warnings
    for warning in warnings_list:
        logger.warning(f"Security configuration warning: {warning}")

    # In production, fail on critical issues
    if issues:
        for issue in issues:
            logger.error(f"CRITICAL security issue: {issue}")
        if is_production:
            raise RuntimeError(
                f"Production deployment blocked due to {len(issues)} security issue(s). "
                f"Check logs and fix configuration before deploying."
            )

    return len(issues) == 0


# Startup event: initialize services and load demo data
@app.on_event("startup")
async def startup_event():
    """Initialize services and demo data on startup."""
    logger.info("RepoLens API starting up...")

    # Validate secrets configuration
    validate_production_secrets()

    # Check Neo4j connectivity and ensure indexes
    try:
        from app.db.neo4j_driver import get_driver
        from app.db.models import ensure_indexes

        driver = get_driver()
        driver.verify_connectivity()
        log_service_startup("neo4j", "ready")
        logger.info("✓ Neo4j connection verified")

        # Ensure database indexes exist for performance
        ensure_indexes()
        logger.info("✓ Neo4j indexes ensured")
    except Exception as e:
        log_service_startup("neo4j", "failed", {"error": str(e)})
        logger.warning(f"Neo4j not available: {e}")

    # Check Redis connectivity
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = Redis.from_url(redis_url)
        r.ping()
        log_service_startup("redis", "ready")
    except Exception as e:
        log_service_startup("redis", "failed", {"error": str(e)})
        logger.warning(f"Redis not available: {e}")

    # Load demo data if configured
    config = get_demo_config()
    if config.enabled and config.auto_load_on_startup:
        logger.info("Scheduling demo data loading...")
        asyncio.create_task(_load_demo_data_with_retry())

    log_service_startup("api", "ready", {"demo_mode": config.enabled})


async def _load_demo_data_with_retry(max_retries: int = 3, delay: int = 5):
    """Load demo data with retry logic and graceful degradation."""
    health_checker = get_health_checker()

    # Use Redis lock to ensure only ONE worker loads demo data
    # This prevents 4 workers from competing/duplicating work
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock = None
    try:
        redis_conn = Redis.from_url(redis_url)
        lock = redis_conn.lock("demo_data_loading_lock", timeout=600)
        acquired = lock.acquire(blocking=False)
        if not acquired:
            logger.info("Another worker is loading demo data, skipping...")
            return
    except Exception as e:
        logger.warning(f"Could not acquire Redis lock, proceeding anyway: {e}")
        lock = None

    try:
        health_checker.set_demo_data_status("loading")

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Loading demo data (attempt {attempt}/{max_retries})...")

                # Check if embedding model is available (set by docker-entrypoint.sh)
                embedding_available = os.getenv("EMBEDDING_MODEL_AVAILABLE", "true").lower() == "true"

                if embedding_available:
                    from app.services.embeddings import CodeEmbedder
                    embedder = CodeEmbedder()
                    stats = initialize_demo_data(embedder=embedder, neo4j_driver=None)
                    logger.info(f"Demo data loaded successfully: {stats}")
                    log_service_startup("demo_data", "ready", stats)
                    health_checker.set_demo_data_status("ready", stats)
                    return
                else:
                    logger.warning("Embedding model not available, skipping demo data with embeddings")
                    log_service_startup("demo_data", "skipped", {"reason": "embedding_model_unavailable"})
                    health_checker.set_demo_data_status("skipped", {"reason": "embedding_model_unavailable"})
                    return

            except Exception as e:
                logger.warning(f"Demo data loading attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)

        logger.error(f"Failed to load demo data after {max_retries} attempts")
        log_service_startup("demo_data", "failed", {"attempts": max_retries})
        health_checker.set_demo_data_status("failed", {"attempts": max_retries})
    finally:
        # Release Redis lock if acquired
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass  # Lock may have expired or been released already


# --- Helper: simulate background parse job ---
async def _simulate_parse_job(repo_id: str):
    total = 8
    for i in range(1, total + 1):
        # simulate work
        await asyncio.sleep(0.7)
        REPOS[repo_id]["status"] = "parsing"
        REPOS[repo_id]["progress"] = {"current": i, "total": total}
        REPOS[repo_id]["lastMessage"] = f"Parsing file {i}/{total}"

    # create a small demo graph for this repo
    nodes = [
        {"id": f"n-{repo_id}-1", "type": "file", "name": "app.js", "path": "/app.js", "summary": "Main app", "lineCount": 120},
        {"id": f"n-{repo_id}-2", "type": "function", "name": "createServer", "path": "/lib/server.js", "summary": "Creates server", "lineCount": 34},
    ]

    edges = [
        {"id": f"e-{repo_id}-1", "source": nodes[0]["id"], "target": nodes[1]["id"], "type": "imports"}
    ]

    GRAPHS[repo_id] = {"nodes": nodes, "edges": edges}

    REPOS[repo_id]["status"] = "complete"
    REPOS[repo_id]["nodeCount"] = len(nodes)
    REPOS[repo_id]["edgeCount"] = len(edges)
    REPOS[repo_id]["fileCount"] = 2
    REPOS[repo_id].pop("progress", None)


def validate_git_url(url: str) -> tuple[bool, str, Optional[str]]:
    """
    Validate and normalize a git URL for security.

    Returns:
        (is_valid, normalized_url, error_message)
    """
    import re
    from urllib.parse import urlparse

    if not url or not isinstance(url, str):
        return False, "", "URL is required"

    url = url.strip()

    # Block dangerous protocols
    dangerous_protocols = ["file://", "ftp://", "data:", "javascript:"]
    url_lower = url.lower()
    for proto in dangerous_protocols:
        if url_lower.startswith(proto):
            return False, "", f"Protocol '{proto}' is not allowed"

    # Block localhost and internal IPs
    blocked_hosts = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.",  # Link-local
        "10.",       # Private Class A
        "172.16.", "172.17.", "172.18.", "172.19.",  # Private Class B (partial)
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",  # Private Class C
    ]

    # Normalize URL
    if url.startswith("github.com"):
        url = f"https://{url}"
    elif url.startswith("git@"):
        # SSH URL - allow but normalize for parsing
        pass
    elif not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Parse and validate
    try:
        if url.startswith("git@"):
            # SSH format: git@github.com:user/repo.git
            match = re.match(r"git@([^:]+):", url)
            host = match.group(1) if match else ""
        else:
            parsed = urlparse(url)
            host = parsed.hostname or ""
    except Exception:
        return False, "", "Invalid URL format"

    host_lower = host.lower()

    # Check for blocked hosts
    for blocked in blocked_hosts:
        if host_lower == blocked or host_lower.startswith(blocked):
            return False, "", f"Internal/local addresses are not allowed"

    # Validate it looks like a git hosting URL
    allowed_hosts = [
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "gitlab.",  # Self-hosted GitLab instances
        "github.",  # GitHub Enterprise
    ]

    # For security, we only allow known git hosting providers
    # This can be relaxed later if needed
    is_known_host = any(
        host_lower == allowed or host_lower.startswith(allowed.rstrip(".") + ".")
        for allowed in allowed_hosts
    )

    if not is_known_host:
        # Allow any HTTPS URL but log it
        if not url.startswith("https://"):
            return False, "", "Only HTTPS URLs are allowed for unknown hosts"
        logger.info(f"Allowing non-standard git host: {host}")

    # Limit URL length
    if len(url) > 2000:
        return False, "", "URL is too long (max 2000 characters)"

    return True, url, None


# --- API endpoints ---
@app.post("/api/repos")
async def create_repo(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    url = payload.get("url") or payload.get("git_url")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    # Validate and normalize URL
    is_valid, url, error = validate_git_url(url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    repo_id = f"repo-{uuid.uuid4().hex[:8]}"

    # Extract repo name from URL
    name = url.rstrip('/').split('/')[-2:] if '/' in url else [url]
    name = '/'.join(name[-2:]) if len(name) >= 2 else url

    logger.info(f"Creating repository", extra={'extra_data': {'repo_id': repo_id, 'url': url, 'user': current_user.get('email')}})

    # Create Repository node in Neo4j (includes user linking)
    from app.db.models import create_repository
    success = create_repository(repo_id, url, name, current_user["github_id"])

    if not success:
        logger.error(f"Failed to create repository in database", extra={'extra_data': {'repo_id': repo_id, 'url': url}})
        raise HTTPException(status_code=500, detail="Failed to create repository in database")

    # Keep in-memory for SSE progress tracking
    repo = Repository(id=repo_id, name=name, url=url, status="queued")
    REPOS[repo_id] = repo.dict()

    # Enqueue task with dynamic timeout
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_conn = Redis.from_url(redis_url)
    q = Queue(connection=redis_conn)
    job_timeout = calculate_job_timeout()  # Default timeout, will handle large repos
    q.enqueue(worker_tasks.parse_and_index, repo_id, url, job_timeout=job_timeout)

    logger.info(f"Repository queued for processing", extra={'extra_data': {'repo_id': repo_id}})

    return REPOS[repo_id]


@app.get("/api/repos")
async def list_repos(current_user: dict = Depends(get_current_user)):
    """List user's repos"""
    user_repos = get_user_repos(current_user["github_id"])
    return user_repos


@app.get("/api/repos/{repo_id}")
async def get_repo(repo_id: str, current_user: dict = Depends(get_current_user_optional)):
    """
    Get repository details by ID.

    Requires authentication unless it's a demo repository.
    """
    from app.demo.config import is_demo_repo

    # Demo repos are publicly accessible, others require authentication
    if not is_demo_repo(repo_id) and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    repo = REPOS.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="not found")
    return repo


@app.delete("/api/repos/{repo_id}")
async def delete_repo(repo_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a repository and all its associated data.

    This endpoint:
    - Verifies the user owns the repository
    - Deletes all nodes (files, classes, functions) from Neo4j
    - Deletes all relationships/edges
    - Deletes the repository record

    Args:
        repo_id: The repository ID to delete
        current_user: The authenticated user (from JWT)

    Returns:
        Success message or error
    """
    github_id = current_user.get("github_id")
    if not github_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Delete from Neo4j
    success = delete_repository(repo_id, github_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Repository not found or you don't have permission to delete it"
        )

    # Also remove from in-memory cache
    if repo_id in REPOS:
        del REPOS[repo_id]
    if repo_id in GRAPHS:
        del GRAPHS[repo_id]

    # Clear any chat history from localStorage (handled on frontend)
    logger.info(f"Repository {repo_id} deleted by user {github_id}")

    return {"success": True, "message": f"Repository {repo_id} deleted successfully"}


# SSE: stream repo parse progress
async def _repo_event_generator(repo_id: str):
    last_state = None
    while True:
        repo = REPOS.get(repo_id)
        if repo is None:
            payload = {"type": "error", "message": "repo not found", "repoId": repo_id}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        state = {"status": repo.get("status"), "progress": repo.get("progress"), "nodeCount": repo.get("nodeCount", 0)}
        if state != last_state:
            payload = {"type": "progress", "repoId": repo_id, "status": state["status"], "progress": state.get("progress")}
            yield f"data: {json.dumps(payload)}\n\n"
            last_state = state

        if repo.get("status") == "complete":
            payload = {"type": "done", "repoId": repo_id}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        await asyncio.sleep(0.5)


@app.get("/api/repos/{repo_id}/events")
async def repo_events(repo_id: str):
    async def generator():
        # Try subscribing to Redis pubsub for progress updates first
        try:
            async for msg in subscribe_progress(repo_id):
                # update in-memory REPOS snapshot to keep compatibility
                try:
                    REPOS.setdefault(repo_id, {"id": repo_id})
                    if "progress" in msg:
                        REPOS[repo_id]["status"] = "parsing"
                        REPOS[repo_id]["progress"] = msg["progress"]
                    if "message" in msg:
                        REPOS[repo_id]["lastMessage"] = msg["message"]
                    # if message says complete mark status
                    if isinstance(msg.get("message"), str) and msg.get("message").lower().startswith("complete"):
                        REPOS[repo_id]["status"] = "complete"
                except Exception as e:
                    logger.debug(f"Non-critical error updating repo status: {e}")

                yield f"data: {json.dumps(msg)}\n\n"

        except Exception as e:
            # If subscribing fails, fall back to polling the in-memory state
            logger.debug(f"Redis pubsub not available, falling back to polling: {e}")

        # fallback: yield from existing generator
        async for evt in _repo_event_generator(repo_id):
            yield evt

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/api/graph/{repo_id}")
async def get_graph(repo_id: str, current_user: dict = Depends(get_current_user_optional)):
    """
    Get the code graph for a repository.

    Requires authentication unless it's a demo repository.
    Uses Redis caching (5 min TTL) for performance.
    """
    from app.db.models import get_graph_by_repo
    from app.demo.config import is_demo_repo

    # For demo repos, allow public access
    if is_demo_repo(repo_id):
        from app.api.demo import get_demo_graph
        return await get_demo_graph(repo_id)

    # Non-demo repos require authentication
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Check Redis cache first
        cache_key = f"graph:{repo_id}"
        try:
            from app.utils.redis_client import get_redis_client
            redis_client = get_redis_client()
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass  # Cache miss or Redis unavailable, continue to DB

        # Fetch from database
        graph = get_graph_by_repo(repo_id)

        # Cache the result (5 minutes TTL)
        try:
            redis_client = get_redis_client()
            redis_client.setex(cache_key, 300, json.dumps(graph))
        except Exception:
            pass  # Caching failed, but still return the data

        return graph
    except Exception as e:
        # Return empty graph shape to keep frontend happy
        return {"nodes": [], "edges": []}


@app.get("/api/graph/{repo_id}/nodes/{node_id}")
async def get_node(repo_id: str, node_id: str):
    from app.demo.config import is_demo_repo

    # For demo repos, get node from demo graph data
    if is_demo_repo(repo_id):
        from app.api.demo import get_demo_graph
        try:
            demo_graph = await get_demo_graph(repo_id)
            node = next((n for n in demo_graph["nodes"] if n["id"] == node_id), None)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            return node
        except Exception as e:
            logger.warning(f"Failed to get demo node: {e}")
            raise HTTPException(status_code=404, detail="demo node not found")

    # For regular repos, check in-memory GRAPHS first
    graph = GRAPHS.get(repo_id)
    if not graph:
        # Try fetching from Neo4j
        try:
            from app.db.models import get_graph_by_repo
            graph = get_graph_by_repo(repo_id)
        except Exception as e:
            logger.debug(f"Could not fetch graph from Neo4j for {repo_id}: {e}")

    if not graph:
        raise HTTPException(status_code=404, detail="repo graph not found")

    node = next((n for n in graph["nodes"] if n["id"] == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")

    # Attach code preview if not present
    node = node.copy()
    if not node.get("code"):
        node["code"] = "// Example code snippet\nconsole.log(\"Hello from " + node.get("name", "node") + "\");"
    return node


@app.get("/api/repos/{repo_id}/insights")
async def get_repo_insights(repo_id: str, current_user: dict = Depends(get_current_user_optional)):
    """
    Get intelligent insights about repository structure and architecture.

    Returns:
    - Entry points (nodes with no incoming dependencies)
    - Complexity hotspots (highly connected nodes)
    - Architecture hubs (central coordination points)
    - Isolated modules (weakly connected components)

    Demo repositories are public; everything else requires authentication.
    """
    from app.db.models import get_graph_by_repo
    from app.demo.config import is_demo_repo
    from app.services.insights import compute_insights

    # Get graph data
    if is_demo_repo(repo_id):
        from app.api.demo import get_demo_graph
        graph = await get_demo_graph(repo_id)
    else:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            graph = get_graph_by_repo(repo_id)
        except Exception as e:
            logger.warning(f"Failed to get graph for insights for {repo_id}: {e}")
            graph = {"nodes": [], "edges": []}

    return compute_insights(
        repo_id,
        graph.get("nodes", []),
        graph.get("edges", []),
    )


# Cache for system prompts (base context without node-specific info)
# Key: repo_id, Value: (timestamp, prompt)
_system_prompt_cache: dict[str, tuple[float, str]] = {}
_PROMPT_CACHE_TTL = 300  # 5 minutes

def _get_cached_base_prompt(repo_id: str, repo_name: str) -> str:
    """Get cached base system prompt for a repository (without node context)."""
    import time
    from app.services.llm.context_builder import build_system_prompt

    cache_key = repo_id
    now = time.time()

    # Check cache
    if cache_key in _system_prompt_cache:
        cached_time, cached_prompt = _system_prompt_cache[cache_key]
        if now - cached_time < _PROMPT_CACHE_TTL:
            return cached_prompt

    # Build and cache
    prompt = build_system_prompt(
        repo_id=repo_id,
        repo_name=repo_name,
        node_id=None,  # Base prompt without node context
        max_readme_chars=2000,
        max_code_chars=2000,
    )
    _system_prompt_cache[cache_key] = (now, prompt)
    return prompt


# Chat streaming SSE endpoint
@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    node_ctx = body.get("nodeContext")  # Could be node name or node ID
    node_id = body.get("node_id")  # Explicit node ID if provided
    messages = body.get("messages") or []
    repo_id = body.get("repo_id")
    repo_name = body.get("repo_name", "Repository")

    # Build rich system prompt with context from Neo4j
    from app.services.llm.context_builder import build_system_prompt, get_node_full_context, NODE_CONTEXT_TEMPLATE, _format_list, _detect_language

    if repo_id:
        # Use cached base prompt for faster response
        if node_id:
            # Node-specific context: use full build for first message, or append to cached base
            system_prompt = build_system_prompt(
                repo_id=repo_id,
                repo_name=repo_name,
                node_id=node_id,
                max_readme_chars=2000,
                max_code_chars=2000,
            )
        else:
            # No node context: use cached base prompt (much faster)
            system_prompt = _get_cached_base_prompt(repo_id, repo_name)
        # Add node context name if only name provided (not full ID)
        if node_ctx and not node_id:
            system_prompt += f"\n\nNote: The user is currently viewing: {node_ctx}"
    else:
        # Fallback for demo mode or when no repo_id
        system_prompt = """You are RepoLens AI, an expert code assistant. You help developers understand their codebase by answering questions about code structure, dependencies, and functionality.

Guidelines:
- Be concise but thorough in your explanations
- Use code examples when helpful
- Reference specific files, functions, or classes when discussing the codebase
- If you don't know something specific about the code, acknowledge it
- Focus on providing actionable insights"""

        if node_ctx:
            system_prompt += f"\n\nThe user is currently viewing: {node_ctx}"

    # Convert messages to LLM format
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        llm_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })

    async def event_generator():
        try:
            # Try to use real LLM
            from app.services.llm import get_llm_client
            llm_client = get_llm_client()

            msg_id = f"msg-{uuid.uuid4().hex[:8]}"

            # Stream response from LLM with optimized max_tokens for chat
            for chunk in llm_client.chat_completion_stream(llm_messages, max_tokens=1500):
                msg = {
                    "type": "delta",
                    "message": {
                        "id": msg_id,
                        "role": "assistant",
                        "content": chunk,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "nodeContext": node_ctx,
                    },
                }
                yield f"data: {json.dumps(msg)}\n\n"

            # Final event
            done = {"type": "done", "message": {"id": msg_id}}
            yield f"data: {json.dumps(done)}\n\n"

        except Exception as e:
            # Log full error details server-side
            logger.error(f"Chat stream error: {e}", exc_info=True)

            # Provide sanitized error message to client (don't leak internal details)
            error_str = str(e).lower()
            if "connection" in error_str or "timeout" in error_str:
                user_message = "I apologize, but I couldn't connect to the AI service. Please try again in a moment."
            elif "rate" in error_str or "limit" in error_str:
                user_message = "I apologize, but the AI service is currently rate limited. Please wait a moment and try again."
            elif "api" in error_str or "key" in error_str or "auth" in error_str:
                user_message = "I apologize, but there was an issue with the AI service configuration. Please contact support if this persists."
            else:
                user_message = "I apologize, but I encountered an unexpected error. Please try again."

            error_msg = {
                "type": "delta",
                "message": {
                    "id": f"msg-{uuid.uuid4().hex[:8]}",
                    "role": "assistant",
                    "content": user_message,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "nodeContext": node_ctx,
                },
            }
            yield f"data: {json.dumps(error_msg)}\n\n"
            done = {"type": "done", "message": {"id": f"msg-{uuid.uuid4().hex[:8]}"}}
            yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Auth endpoints
@app.get("/api/auth/github")
async def login_github():
    """Redirect to GitHub OAuth login"""
    auth_url, state = await get_github_auth_url()
    return RedirectResponse(url=auth_url, status_code=303)

@app.get("/api/auth/github/callback")
async def github_callback(code: str, state: str):
    """GitHub calls this after user approves"""
    import logging
    logger = logging.getLogger(__name__)

    # Exchange code for token
    access_token = await exchange_code_for_token(code, state)
    if not access_token:
        logger.error(f"OAuth callback failed: Invalid or expired state token. State: {state[:10]}...")
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=invalid_state", status_code=303)

    # Get user info
    github_user = await get_github_user(access_token)
    if not github_user:
        logger.error("OAuth callback failed: Unable to fetch GitHub user info after successful token exchange")
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=failed_to_get_user", status_code=303)

    # Create/update user in DB
    github_id = github_user["id"]
    email = github_user.get("email") or f"{github_user['login']}@github.com"
    name = github_user.get("name") or github_user["login"]
    avatar_url = github_user.get("avatar_url", "")

    create_or_update_user(github_id, email, name, avatar_url)
    logger.info(f"OAuth success: User {email} (GitHub ID: {github_id}) authenticated successfully")

    # Create access and refresh tokens
    from app.auth.jwt_handler import create_access_token, create_refresh_token

    user_data = {
        "github_id": github_id,
        "email": email,
        "name": name,
        "avatar_url": avatar_url,
    }

    access_token = create_access_token(user_data)
    refresh_token_str = create_refresh_token(user_data)

    # Encode user data for URL (minimal info for frontend)
    import urllib.parse
    user_info = urllib.parse.quote(json.dumps({
        "github_id": user_data.get("github_id"),
        "username": name,
        "email": user_data.get("email"),
        "avatar_url": user_data.get("avatar_url"),
    }))

    # Redirect with tokens in URL fragment (fragment is NOT sent to server, only available to client JS)
    # This is the industry standard approach for SPAs with separate frontend/backend domains
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"#access_token={access_token}"
        f"&refresh_token={refresh_token_str}"
        f"&user={user_info}"
    )

    logger.info(f"User {github_id} authenticated via GitHub OAuth")
    return RedirectResponse(url=redirect_url, status_code=303)

@app.post("/api/auth/logout")
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """Logout user by blacklisting their current token and clearing cookie"""
    from fastapi.responses import JSONResponse
    from app.auth.token_blacklist import get_token_blacklist
    from app.auth.jwt_handler import SECRET_KEY, ALGORITHM

    try:
        # Extract token from Authorization header or cookie
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
        elif "auth_token" in request.cookies:
            token = request.cookies.get("auth_token")

        if token:
            try:
                # Decode to get jti and expiration
                payload = jwt.decode(
                    token,
                    SECRET_KEY,
                    algorithms=[ALGORITHM],
                    options={"verify_signature": False}
                )
                jti = payload.get("jti")
                exp = payload.get("exp")

                if jti and exp:
                    # Convert exp timestamp to datetime
                    expires_at = datetime.utcfromtimestamp(exp)

                    # Blacklist the token
                    blacklist = get_token_blacklist()
                    blacklist.blacklist_token(jti, expires_at)

                    logger.info(f"User {current_user.get('github_id')} logged out, token blacklisted")
            except jwt.InvalidTokenError as e:
                # Token is malformed, but that's okay - still log them out
                logger.warning(f"Invalid token during logout: {e}")
            except Exception as e:
                # Any other error during blacklisting - still proceed with logout
                logger.error(f"Error blacklisting token during logout: {e}")

        # Create response and clear both auth cookies
        # Cookie deletion must match the parameters used when setting them
        response = JSONResponse(content={"message": "logged out successfully"})
        response.delete_cookie(
            key="auth_token",
            path="/",
            secure=True,
            samesite="none",
        )
        response.delete_cookie(
            key="refresh_token",
            path="/",
            secure=True,
            samesite="none",
        )

        return response
    except Exception as e:
        logger.error(f"Logout error: {e}")
        is_production = os.getenv("APP_ENV", "development") == "production"
        response = JSONResponse(content={"message": "logged out"})
        response.delete_cookie(
            key="auth_token",
            path="/",
            secure=is_production,
            samesite="lax",
        )
        response.delete_cookie(
            key="refresh_token",
            path="/",
            secure=is_production,
            samesite="lax",
        )
        return response

@app.post("/api/auth/refresh")
async def refresh_token(request: Request):
    """
    Refresh access token using refresh token.

    This endpoint allows clients to obtain a new access token
    without requiring the user to log in again.

    Accepts refresh token from:
    - JSON body: {"refresh_token": "..."}
    - Cookie (fallback for backwards compatibility)
    """
    from fastapi.responses import JSONResponse
    from app.auth.jwt_handler import (
        verify_token,
        create_access_token,
        create_refresh_token,
        SECRET_KEY,
        ALGORITHM
    )

    # Try to get refresh token from JSON body first
    refresh_token_str = None
    try:
        body = await request.json()
        refresh_token_str = body.get("refresh_token")
    except:
        pass

    # Fallback to cookie for backwards compatibility
    if not refresh_token_str:
        refresh_token_str = request.cookies.get("refresh_token")

    if not refresh_token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided"
        )

    # Verify refresh token
    payload = verify_token(refresh_token_str)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Verify it's actually a refresh token
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    # Create new access token
    user_data = {
        "github_id": payload.get("github_id"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "avatar_url": payload.get("avatar_url"),
    }

    new_access_token = create_access_token(user_data)

    # Return new access token in JSON response (for localStorage-based auth)
    return JSONResponse(content={
        "message": "Token refreshed successfully",
        "access_token": new_access_token,
        "user": user_data
    })

@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    return current_user


# Health endpoints
@app.get("/health")
async def health():
    """Basic health check - returns ok if service is running"""
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@app.get("/health/detailed")
async def health_detailed():
    """
    Detailed health check with all component statuses.

    Returns status of Neo4j, Redis, embedding model, worker, and demo data.
    """
    health_checker = get_health_checker()
    return await health_checker.get_detailed_health()


@app.get("/health/ready")
async def health_ready():
    """
    Readiness probe for Kubernetes/container orchestration.

    Returns 200 if critical services (Neo4j, Redis) are healthy.
    Returns 503 if service is not ready to accept requests.
    """
    from fastapi.responses import JSONResponse

    health_checker = get_health_checker()
    is_ready, details = await health_checker.is_ready()

    if is_ready:
        return JSONResponse(
            status_code=200,
            content={"ready": True, **details}
        )
    else:
        return JSONResponse(
            status_code=503,
            content={"ready": False, **details}
        )
