"""
Worker tasks for repository processing.

Handles:
- Repository cloning and parsing
- Embedding generation for semantic search
- LLM summarization (optional)
- Progress tracking and persistence
"""

import json
import os
import asyncio
import time
import logging
import traceback
from enum import Enum
from typing import Any, Optional, Dict
from dataclasses import dataclass, field

from redis import Redis

from app.services.parser import parse_repository
from app.db.models import create_nodes_and_edges, update_task_status, clear_task_status
from app.services.embeddings import CodeEmbedder
from app.db.vector_store import language_for_path, store_node_embeddings
from app.services.llm import CodeSummarizer, DeepSeekClient

# Configure logging for worker
from app.utils.logging_config import configure_logging, get_logger

configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name=os.getenv("SERVICE_NAME", "repolens-worker")
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Code elements embedded (and written to Neo4j) per round trip. embed_batch is
# much faster than one call per node, and one UNWIND beats 200 round-trips.
EMBED_BATCH_SIZE = 200

logger = get_logger(__name__)

# Module-level singleton for embedder to avoid re-downloading model on each job
_embedder_instance: Optional[CodeEmbedder] = None


def get_embedder() -> CodeEmbedder:
    """Get or create a singleton CodeEmbedder instance."""
    global _embedder_instance
    if _embedder_instance is None:
        logger.info("Initializing CodeEmbedder singleton...")
        _embedder_instance = CodeEmbedder()
    return _embedder_instance




class TaskStep(str, Enum):
    """Task processing steps"""
    INITIALIZING = "initializing"
    CLONING = "cloning"
    PARSING = "parsing"
    PERSISTING = "persisting"
    EMBEDDING = "embedding"
    SUMMARIZING = "summarizing"
    FINALIZING = "finalizing"


class TaskStatus(str, Enum):
    """Task status values"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class TaskContext:
    """Context for tracking task execution"""
    repo_id: str
    url: str
    start_time: float = field(default_factory=time.time)
    current_step: TaskStep = TaskStep.INITIALIZING
    nodes_count: int = 0
    edges_count: int = 0
    files_count: int = 0
    functions_indexed: int = 0
    classes_indexed: int = 0
    summaries_generated: int = 0
    warnings: list = field(default_factory=list)

    def elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        return time.time() - self.start_time


def publish_progress(repo_id: str, current: int, total: int, message: str = ""):
    """Publish progress to Redis pubsub for real-time frontend updates"""
    try:
        r = Redis.from_url(REDIS_URL)
        payload = {
            "repoId": repo_id,
            "progress": {"current": current, "total": total},
            "message": message
        }
        channel = f"progress:{repo_id}"
        r.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning(f"Failed to publish progress for {repo_id}: {e}")
        # Don't crash the task if progress publishing fails


def publish_progress_detailed(
    ctx: TaskContext,
    progress_pct: int,
    message: str,
    status: TaskStatus = TaskStatus.IN_PROGRESS,
    error: Optional[str] = None,
):
    """
    Enhanced progress publishing with step tracking and persistence.

    Publishes to both Redis (real-time) and Neo4j (persistence).
    """
    # Calculate ETA based on progress
    elapsed = ctx.elapsed_time()
    if progress_pct > 0 and progress_pct < 100:
        # Estimate remaining time: (elapsed / progress%) * (100 - progress%)
        rate = elapsed / progress_pct  # seconds per percent
        eta_seconds = rate * (100 - progress_pct)
    else:
        eta_seconds = 0

    # Calculate processing rate (items per second)
    processing_rate = ctx.nodes_count / max(elapsed, 1) if ctx.nodes_count > 0 else 0

    # Build metadata
    metadata = {
        "elapsed_seconds": round(elapsed, 2),
        "eta_seconds": round(eta_seconds, 1),
        "processing_rate": round(processing_rate, 2),
        "nodes_count": ctx.nodes_count,
        "edges_count": ctx.edges_count,
        "files_count": ctx.files_count,
    }

    if ctx.functions_indexed > 0:
        metadata["functions_indexed"] = ctx.functions_indexed
    if ctx.classes_indexed > 0:
        metadata["classes_indexed"] = ctx.classes_indexed
    if ctx.summaries_generated > 0:
        metadata["summaries_generated"] = ctx.summaries_generated
    if ctx.warnings:
        metadata["warnings"] = ctx.warnings[-5:]  # Last 5 warnings

    # Publish to Redis for real-time updates
    try:
        r = Redis.from_url(REDIS_URL)
        payload = {
            "repoId": ctx.repo_id,
            "step": ctx.current_step.value,
            "status": status.value,
            "progress": {"current": progress_pct, "total": 100},
            "message": message,
            "metadata": metadata,
        }
        if error:
            payload["error"] = error

        # Add 'type: done' when task is completed to signal frontend
        if status == TaskStatus.COMPLETED:
            payload["type"] = "done"

        channel = f"progress:{ctx.repo_id}"
        r.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning(f"Failed to publish progress for {ctx.repo_id}: {e}")

    # Persist to Neo4j
    try:
        update_task_status(
            repo_id=ctx.repo_id,
            step=ctx.current_step.value,
            status=status.value,
            progress_pct=progress_pct,
            message=message,
            error=error,
            metadata=metadata,
        )
    except Exception as e:
        logger.warning(f"Failed to persist task status for {ctx.repo_id}: {e}")


def parse_and_persist(repo_id: str, url: str):
    """RQ task: parse repository and persist to Neo4j, publishing progress to Redis."""
    from app.db.models import update_repository_status

    # parse_repository is async; run it in an event loop
    try:
        # Mark as parsing
        update_repository_status(repo_id, "parsing")

        nodes, edges = asyncio.run(parse_repository(repo_id, url, options=None, progress_callback=lambda c, t, m: publish_progress(repo_id, c, t, m)))
        # persist
        create_nodes_and_edges(repo_id, nodes, edges)

        # Count files
        file_count = sum(1 for n in nodes if n.get('type', '').lower() == 'file')

        # Mark as complete with stats
        update_repository_status(
            repo_id, "complete",
            node_count=len(nodes),
            edge_count=len(edges),
            file_count=file_count
        )

        # final progress
        publish_progress(repo_id, current=len(nodes), total=len(nodes), message="complete")
    except Exception as exc:
        update_repository_status(repo_id, "error")
        publish_progress(repo_id, current=0, total=0, message=f"error: {str(exc)}")
        logger.error(f"Failed to parse {repo_id}: {exc}", exc_info=True)
        raise


def parse_and_index(
    repo_id: str,
    url: str,
    generate_embeddings: bool = True,
    generate_summaries: bool = False,
):
    """
    Enhanced RQ task: parse, generate embeddings, and optionally summarize code.

    This is the new default task that includes:
    - Repository parsing with detailed progress tracking
    - Embedding generation for semantic search
    - Optional LLM summarization
    - Neo4j persistence
    - Error isolation (embedding/summary failures don't fail the task)
    """
    from app.db.models import update_repository_status
    import time

    # Initialize task context
    ctx = TaskContext(repo_id=repo_id, url=url)

    # PERFORMANCE PROFILING: Track timing for each major operation
    perf_timings = {}
    task_start = time.time()

    logger.info(
        f"Starting parse_and_index task",
        extra={'extra_data': {
            'repo_id': repo_id,
            'url': url,
            'generate_embeddings': generate_embeddings,
            'generate_summaries': generate_summaries,
        }}
    )

    try:
        # Step 1: Initialize (0-5%)
        ctx.current_step = TaskStep.INITIALIZING
        publish_progress_detailed(ctx, 0, "Initializing task...")
        update_repository_status(repo_id, "parsing")

        # Step 2: Clone and Parse (5-40%)
        ctx.current_step = TaskStep.PARSING
        publish_progress_detailed(ctx, 5, "Cloning and parsing repository...")
        logger.info(f"Parsing repository {repo_id}", extra={'extra_data': {'repo_id': repo_id, 'url': url}})

        def parsing_progress_callback(current: int, total: int, message: str):
            # Map parsing progress to 5-40% range
            pct = 5 + int((current / max(total, 1)) * 35)
            publish_progress_detailed(ctx, pct, f"Parsing: {message}")

        t0 = time.time()
        nodes, edges = asyncio.run(
            parse_repository(
                repo_id,
                url,
                options=None,
                progress_callback=parsing_progress_callback
            )
        )
        perf_timings['clone_and_parse'] = round(time.time() - t0, 2)

        ctx.nodes_count = len(nodes)
        ctx.edges_count = len(edges)
        ctx.files_count = sum(1 for n in nodes if n.get('type', '').lower() == 'file')

        logger.info(
            f"Parsed {ctx.nodes_count} nodes and {ctx.edges_count} edges for {repo_id}",
            extra={'extra_data': {
                'repo_id': repo_id,
                'nodes_count': ctx.nodes_count,
                'edges_count': ctx.edges_count,
                'files_count': ctx.files_count,
            }}
        )

        publish_progress_detailed(ctx, 40, f"Parsed {ctx.nodes_count} nodes from {ctx.files_count} files")

        # Step 3: Persist to Neo4j (40-50%)
        ctx.current_step = TaskStep.PERSISTING
        publish_progress_detailed(ctx, 42, "Persisting to database...")
        logger.info(f"Persisting {ctx.nodes_count} nodes to Neo4j", extra={'extra_data': {'repo_id': repo_id}})

        t0 = time.time()
        create_nodes_and_edges(repo_id, nodes, edges)
        perf_timings['neo4j_persist'] = round(time.time() - t0, 2)

        publish_progress_detailed(ctx, 50, "Database updated")

        # Step 4: Generate embeddings (50-80%)
        if generate_embeddings:
            ctx.current_step = TaskStep.EMBEDDING
            try:
                publish_progress_detailed(ctx, 52, "Generating embeddings for semantic search...")
                logger.info(f"Generating embeddings for {repo_id}", extra={'extra_data': {'repo_id': repo_id}})

                t0 = time.time()
                ctx.functions_indexed, ctx.classes_indexed = _generate_embeddings_for_repo(repo_id, nodes, ctx)
                perf_timings['embedding'] = round(time.time() - t0, 2)

                logger.info(
                    f"Indexed {ctx.functions_indexed} functions and {ctx.classes_indexed} classes for {repo_id}",
                    extra={'extra_data': {
                        'repo_id': repo_id,
                        'functions_indexed': ctx.functions_indexed,
                        'classes_indexed': ctx.classes_indexed,
                    }}
                )

                publish_progress_detailed(ctx, 80, f"Indexed {ctx.functions_indexed} functions, {ctx.classes_indexed} classes")

            except Exception as e:
                error_msg = f"Embedding generation failed: {str(e)[:200]}"
                ctx.warnings.append(error_msg)
                logger.error(f"Failed to generate embeddings for {repo_id}: {e}", exc_info=True)
                publish_progress_detailed(ctx, 80, "Warning: Embedding generation failed")
        else:
            publish_progress_detailed(ctx, 80, "Skipping embeddings (disabled)")

        # Step 5: Generate LLM summaries (80-95%)
        if generate_summaries:
            ctx.current_step = TaskStep.SUMMARIZING
            try:
                publish_progress_detailed(ctx, 82, "Generating AI summaries...")
                logger.info(f"Generating summaries for {repo_id}", extra={'extra_data': {'repo_id': repo_id}})

                t0 = time.time()
                ctx.summaries_generated = _generate_summaries_for_repo(repo_id, nodes, ctx)
                perf_timings['summarization'] = round(time.time() - t0, 2)

                logger.info(
                    f"Generated {ctx.summaries_generated} AI summaries for {repo_id}",
                    extra={'extra_data': {
                        'repo_id': repo_id,
                        'summaries_generated': ctx.summaries_generated,
                    }}
                )

                publish_progress_detailed(ctx, 95, f"Generated {ctx.summaries_generated} summaries")

            except Exception as e:
                error_msg = f"Summary generation failed: {str(e)[:200]}"
                ctx.warnings.append(error_msg)
                logger.error(f"Failed to generate summaries for {repo_id}: {e}", exc_info=True)
                publish_progress_detailed(ctx, 95, "Warning: Summary generation failed")
        else:
            publish_progress_detailed(ctx, 95, "Skipping summaries (disabled)")

        # Step 6: Finalize (95-100%)
        ctx.current_step = TaskStep.FINALIZING
        publish_progress_detailed(ctx, 98, "Finalizing...")

        # Mark as complete with stats
        update_repository_status(
            repo_id, "complete",
            node_count=ctx.nodes_count,
            edge_count=ctx.edges_count,
            file_count=ctx.files_count
        )

        # Clear task status (we're done)
        clear_task_status(repo_id)

        elapsed = ctx.elapsed_time()
        completion_msg = f"Complete in {elapsed:.1f}s"
        if ctx.warnings:
            completion_msg += f" (with {len(ctx.warnings)} warning(s))"

        publish_progress_detailed(ctx, 100, completion_msg, status=TaskStatus.COMPLETED)

        # PERFORMANCE PROFILING: Log detailed timing breakdown
        perf_timings['total'] = round(elapsed, 2)
        logger.info(
            f"Performance breakdown for {repo_id}: {perf_timings}",
            extra={'extra_data': {
                'repo_id': repo_id,
                'performance_timings': perf_timings,
            }}
        )

        logger.info(
            f"Repository {repo_id} fully indexed in {elapsed:.2f}s",
            extra={'extra_data': {
                'repo_id': repo_id,
                'duration_seconds': round(elapsed, 2),
                'nodes_count': ctx.nodes_count,
                'edges_count': ctx.edges_count,
                'files_count': ctx.files_count,
                'functions_indexed': ctx.functions_indexed,
                'classes_indexed': ctx.classes_indexed,
                'summaries_generated': ctx.summaries_generated,
                'warnings_count': len(ctx.warnings),
            }}
        )

    except Exception as exc:
        elapsed = ctx.elapsed_time()
        error_trace = traceback.format_exc()[-500:]  # Last 500 chars of traceback

        logger.error(
            f"Task failed for {repo_id} after {elapsed:.2f}s: {exc}",
            extra={'extra_data': {
                'repo_id': repo_id,
                'url': url,
                'step': ctx.current_step.value,
                'duration_seconds': round(elapsed, 2),
                'error': str(exc),
                'traceback': error_trace,
            }},
            exc_info=True
        )

        update_repository_status(repo_id, "error")
        publish_progress_detailed(
            ctx, 0,
            f"Failed at {ctx.current_step.value}: {str(exc)[:100]}",
            status=TaskStatus.FAILED,
            error=str(exc)[:500]
        )
        raise


def _generate_embeddings_for_repo(repo_id: str, nodes: list, ctx: TaskContext) -> tuple:
    """
    Generate embeddings for all code in a repository and store them in Neo4j.

    The vectors go onto the (:Node) nodes themselves rather than into an
    in-process list, so the API process (and any later worker) can see them.

    Returns:
        Tuple of (function_count, class_count)
    """
    embedder = get_embedder()

    todo = [n for n in nodes if str(n.get("type", "")).lower() in ("function", "class")]
    total_indexable = len(todo)
    if not total_indexable:
        return 0, 0

    function_count = 0
    class_count = 0
    processed = 0

    for i in range(0, total_indexable, EMBED_BATCH_SIZE):
        batch = todo[i:i + EMBED_BATCH_SIZE]

        texts = [
            "{} {}\n{}\n{}".format(
                node.get("type", ""),
                node.get("name", ""),
                node.get("summary") or node.get("docstring") or "",
                node.get("code", "") or "",
            )
            for node in batch
        ]

        try:
            vectors = embedder.embed_batch(texts)
        except Exception as e:
            logger.warning(f"Failed to embed batch at offset {i}: {e}")
            ctx.warnings.append(f"Embedding batch: {str(e)[:50]}")
            continue

        rows = []
        for node, vector in zip(batch, vectors):
            rows.append({
                "id": node.get("id"),
                "embedding": [float(x) for x in vector],
                "language": language_for_path(node.get("path", "")),
            })

        try:
            store_node_embeddings(rows)
        except Exception as e:
            logger.warning(f"Failed to store embeddings at offset {i}: {e}")
            ctx.warnings.append(f"Embedding storage: {str(e)[:50]}")
            continue

        for node in batch:
            if str(node.get("type", "")).lower() == "function":
                function_count += 1
            else:
                class_count += 1

        processed += len(batch)
        publish_progress_detailed(
            ctx,
            40 + int((processed / total_indexable) * 35),
            f"Embedded {processed}/{total_indexable} code elements",
        )

    return function_count, class_count


def _generate_summaries_for_repo(repo_id: str, nodes: list, ctx: TaskContext) -> int:
    """
    Generate LLM summaries for key code elements.

    Returns:
        Number of summaries generated
    """
    # Check if LLM is configured
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set, skipping summarization")
        ctx.warnings.append("DEEPSEEK_API_KEY not configured")
        return 0

    redis_client = Redis.from_url(REDIS_URL)
    llm_client = DeepSeekClient(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        redis_client=redis_client,
    )
    summarizer = CodeSummarizer(client=llm_client)

    # Summarize top-level functions and classes
    summarized = 0
    max_summaries = 20  # Limit to avoid excessive costs

    summarizable = [n for n in nodes if n.get("type", "").lower() in ["function", "class"]][:max_summaries]

    for i, node in enumerate(summarizable):
        node_type = node.get("type", "").lower()

        try:
            code = node.get("code", "")
            if not code or len(code) < 50:  # Skip trivial code
                continue

            result = summarizer.summarize_code(
                code=code,
                language="python",  # TODO: detect language
                context=f"{node_type}: {node.get('name')}",
            )

            # Store summary back to node (in production, update Neo4j)
            node["ai_summary"] = result["summary"]
            summarized += 1

            logger.debug(f"Summarized {node_type} {node.get('name')}")

        except Exception as e:
            logger.warning(f"Failed to summarize {node.get('name')}: {e}")
            ctx.warnings.append(f"Summary {node.get('name')}: {str(e)[:50]}")

        # Update progress
        if i % 5 == 0:
            pct = 80 + int((i / len(summarizable)) * 15)
            publish_progress_detailed(ctx, pct, f"Summarizing... ({i}/{len(summarizable)})")

    return summarized
