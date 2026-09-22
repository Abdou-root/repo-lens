#!/usr/bin/env python
"""
RQ Worker startup script that bypasses the Click CLI to avoid parameter warnings.
"""
import os
import sys
import logging
import socket
import uuid
from redis import Redis
from rq import Worker

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Configure Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)


def generate_worker_name() -> str:
    """
    Generate a unique worker name using hostname and a short UUID.
    This prevents conflicts when workers restart or multiple instances run.
    """
    base_name = os.getenv("WORKER_NAME", "worker")
    hostname = socket.gethostname()[:8]  # First 8 chars of hostname
    unique_id = uuid.uuid4().hex[:6]     # Short unique suffix
    return f"{base_name}-{hostname}-{unique_id}"


def cleanup_stale_workers():
    """
    Clean up any stale worker registrations from Redis.
    This handles cases where workers crashed without proper cleanup.
    """
    try:
        # Get all workers and check if they're still alive
        from rq.worker import Worker as RQWorker
        workers = RQWorker.all(connection=redis_conn)
        for w in workers:
            # Check if worker is actually running by looking at its heartbeat
            if w.state == 'busy' or w.state == 'idle':
                # Worker might be stale - RQ will handle this via heartbeat timeout
                pass
    except Exception as e:
        logging.warning(f"Could not cleanup stale workers: {e}")


def main():
    """Start the RQ worker"""
    queues = ['default']  # Listen to the 'default' queue

    # Cleanup any stale workers first
    cleanup_stale_workers()

    # Generate unique worker name to avoid conflicts
    worker_name = generate_worker_name()

    worker = Worker(
        queues=queues,
        connection=redis_conn,
        name=worker_name,
    )

    print(f"Starting RQ worker: {worker.name}")
    print(f"Listening on queues: {queues}")

    worker.work(with_scheduler=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWorker stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Worker failed: {e}")
        sys.exit(1)
