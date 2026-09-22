"""
Centralized logging configuration for RepoLens.

Provides:
- Structured JSON logging for production
- Human-readable format for development
- Request correlation ID support
- Service startup logging helpers
"""

import logging
import sys
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar
import uuid

# Context variable for request correlation
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": os.getenv("SERVICE_NAME", "repolens-api"),
        }

        # Add correlation ID if available
        corr_id = correlation_id.get()
        if corr_id:
            log_data["correlation_id"] = corr_id

        # Add extra fields from record
        if hasattr(record, 'extra_data') and record.extra_data:
            log_data["extra_data"] = record.extra_data

        # Add specific fields if present
        for field in ['repo_id', 'url', 'step', 'status', 'duration']:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ReadableFormatter(logging.Formatter):
    """Human-readable format for development."""

    def format(self, record: logging.LogRecord) -> str:
        corr_id = correlation_id.get()
        corr_str = f"[{corr_id[:8]}] " if corr_id else ""

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')

        # Build message
        msg = f"{timestamp} | {record.levelname:8} | {corr_str}{record.name} | {record.getMessage()}"

        # Add exception if present
        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"

        return msg


def configure_logging(
    level: str = "INFO",
    json_format: bool = None,
    service_name: str = "repolens-api"
) -> logging.Logger:
    """
    Configure centralized logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Use JSON format (auto-detected from APP_ENV if None)
        service_name: Service identifier for logs

    Returns:
        Configured root logger
    """
    os.environ["SERVICE_NAME"] = service_name

    # Auto-detect format from environment
    if json_format is None:
        json_format = os.getenv("APP_ENV", "development") == "production"

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ReadableFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)

    # Reduce verbosity of third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def set_correlation_id(request_id: Optional[str] = None) -> str:
    """
    Set correlation ID for request tracing.

    Args:
        request_id: Optional request ID to use, generates UUID if None

    Returns:
        The correlation ID that was set
    """
    corr_id = request_id or str(uuid.uuid4())
    correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return correlation_id.get()


def log_with_context(logger: logging.Logger, level: int, message: str, **kwargs):
    """
    Log a message with additional context fields.

    Args:
        logger: Logger instance
        level: Log level (e.g., logging.INFO)
        message: Log message
        **kwargs: Additional context fields to include
    """
    extra = {'extra_data': kwargs} if kwargs else {}
    logger.log(level, message, extra=extra)


def log_service_startup(service: str, status: str, details: Optional[Dict[str, Any]] = None):
    """
    Log service startup status.

    Args:
        service: Service name (e.g., 'neo4j', 'redis', 'api')
        status: Status ('ready', 'failed', 'starting', etc.)
        details: Optional additional details
    """
    logger = logging.getLogger("startup")
    extra_data = {"service": service, "status": status}
    if details:
        extra_data.update(details)

    record_extra = {'extra_data': extra_data}

    if status == "ready":
        logger.info(f"Service {service} is ready", extra=record_extra)
    elif status == "failed":
        logger.error(f"Service {service} failed to start", extra=record_extra)
    elif status == "degraded":
        logger.warning(f"Service {service} is degraded", extra=record_extra)
    elif status == "skipped":
        logger.info(f"Service {service} skipped", extra=record_extra)
    else:
        logger.info(f"Service {service}: {status}", extra=record_extra)


def log_task_progress(
    repo_id: str,
    step: str,
    status: str,
    progress_pct: int,
    message: str,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Log task progress for repository operations.

    Args:
        repo_id: Repository ID
        step: Current step name
        status: Step status
        progress_pct: Progress percentage (0-100)
        message: Human-readable message
        error: Error message if failed
        metadata: Additional metadata
    """
    logger = logging.getLogger("task")
    extra_data = {
        "repo_id": repo_id,
        "step": step,
        "status": status,
        "progress_pct": progress_pct,
    }
    if error:
        extra_data["error"] = error
    if metadata:
        extra_data["metadata"] = metadata

    record_extra = {'extra_data': extra_data}

    if status == "failed":
        logger.error(f"[{repo_id}] {step}: {message}", extra=record_extra)
    elif status == "completed":
        logger.info(f"[{repo_id}] {step}: {message}", extra=record_extra)
    else:
        logger.info(f"[{repo_id}] {step} ({progress_pct}%): {message}", extra=record_extra)
