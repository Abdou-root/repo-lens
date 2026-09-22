#!/bin/sh
# Docker entrypoint script for RepoLens
# Validates dependencies, waits for services, and optionally pre-downloads model

set -e

# Logging helper with timestamps
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ENTRYPOINT] $1"
}

log "Starting RepoLens initialization..."

# ---------------------------------------------------------
# Step 1: Verify tree-sitter packages
# ---------------------------------------------------------
log "Checking tree-sitter dependencies..."
python -c "import tree_sitter_python; import tree_sitter_javascript; import tree_sitter_typescript" || {
    log "ERROR: tree-sitter packages not found!"
    log "This should not happen. Please rebuild the Docker image with: docker-compose build --no-cache"
    exit 1
}
log "OK: tree-sitter dependencies verified"

# ---------------------------------------------------------
# Step 2: Wait for Neo4j (if NEO4J_URI is set)
# ---------------------------------------------------------
if [ -n "$NEO4J_URI" ]; then
    log "Waiting for Neo4j at $NEO4J_URI..."

    # Extract host and port from NEO4J_URI (bolt://host:port)
    NEO4J_HOST=$(echo "$NEO4J_URI" | sed 's|bolt://||' | cut -d: -f1)
    NEO4J_PORT=$(echo "$NEO4J_URI" | sed 's|bolt://||' | cut -d: -f2)

    MAX_ATTEMPTS=30
    ATTEMPT=1
    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        if nc -z "$NEO4J_HOST" "$NEO4J_PORT" 2>/dev/null; then
            log "OK: Neo4j is ready"
            break
        fi
        log "Waiting for Neo4j... ($ATTEMPT/$MAX_ATTEMPTS)"
        sleep 2
        ATTEMPT=$((ATTEMPT + 1))
    done

    if [ $ATTEMPT -gt $MAX_ATTEMPTS ]; then
        log "WARNING: Neo4j not available after $MAX_ATTEMPTS attempts, continuing anyway..."
    fi
fi

# ---------------------------------------------------------
# Step 3: Wait for Redis (if REDIS_URL is set)
# ---------------------------------------------------------
if [ -n "$REDIS_URL" ]; then
    log "Waiting for Redis..."

    # Extract host and port from REDIS_URL (redis://host:port/db)
    REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
    REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2 | cut -d/ -f1)

    MAX_ATTEMPTS=15
    ATTEMPT=1
    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        if nc -z "$REDIS_HOST" "$REDIS_PORT" 2>/dev/null; then
            log "OK: Redis is ready"
            break
        fi
        log "Waiting for Redis... ($ATTEMPT/$MAX_ATTEMPTS)"
        sleep 1
        ATTEMPT=$((ATTEMPT + 1))
    done

    if [ $ATTEMPT -gt $MAX_ATTEMPTS ]; then
        log "WARNING: Redis not available after $MAX_ATTEMPTS attempts, continuing anyway..."
    fi
fi

# ---------------------------------------------------------
# Step 4: Pre-download embedding model (if PRELOAD_MODEL=true)
# ---------------------------------------------------------
if [ "$PRELOAD_MODEL" = "true" ]; then
    log "Pre-downloading embedding model..."

    MODEL_NAME="${EMBEDDING_MODEL:-all-MiniLM-L6-v2}"
    MAX_ATTEMPTS=3
    ATTEMPT=1

    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        if python -c "
from sentence_transformers import SentenceTransformer
print('Downloading model: $MODEL_NAME')
model = SentenceTransformer('$MODEL_NAME')
print('Model dimension:', model.get_sentence_embedding_dimension())
" 2>&1; then
            log "OK: Embedding model ready"
            export EMBEDDING_MODEL_AVAILABLE=true
            break
        fi
        log "Model download attempt $ATTEMPT/$MAX_ATTEMPTS failed, retrying..."
        ATTEMPT=$((ATTEMPT + 1))
        sleep 5
    done

    if [ $ATTEMPT -gt $MAX_ATTEMPTS ]; then
        log "WARNING: Could not download embedding model, demo features may be limited"
        export EMBEDDING_MODEL_AVAILABLE=false
    fi
else
    log "Skipping model pre-download (PRELOAD_MODEL not set)"
    export EMBEDDING_MODEL_AVAILABLE=true
fi

# ---------------------------------------------------------
# Complete: Start the application
# ---------------------------------------------------------
log "Initialization complete, starting application..."

# Execute the main command
exec "$@"
