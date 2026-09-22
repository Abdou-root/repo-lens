#!/bin/bash
# RepoLens Production Startup Script
# Runs both API server and RQ worker in a single container

set -e

echo "Starting RepoLens..."

# Start RQ worker in background
echo "Starting background worker..."
python run_worker.py &
WORKER_PID=$!

# Give worker a moment to initialize
sleep 2

# Start API server (this blocks and becomes the main process)
echo "Starting API server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
