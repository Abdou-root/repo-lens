# Multi-stage build for RepoLens Backend
# Use bookworm instead of slim for stable OpenSSL 3.0.x (slim has buggy 3.5.4)
FROM python:3.11-bookworm as builder

# Install build dependencies including stable SSL libraries
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    ca-certificates \
    openssl \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies (system-wide for Docker)
RUN pip install --no-cache-dir -r requirements.txt

# Development stage (for local development with volume mounts)
FROM builder as development

WORKDIR /app

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest>=7.0 \
    ipython>=8.0 \
    black>=23.0

# Create non-root user
RUN useradd -m -u 1000 repolens && \
    chown -R repolens:repolens /app /usr/local
    
ENV HF_HOME=/app/cache/huggingface
ENV TRANSFORMERS_CACHE=/app/cache/huggingface
ENV TORCH_HOME=/app/cache/torch

# Create writable cache directories
RUN mkdir -p /app/cache/huggingface /app/cache/torch \
 && chown -R repolens:repolens /app/cache

USER repolens

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=development

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
# Use bookworm for stable OpenSSL 3.0.x
FROM python:3.11-bookworm

# Install runtime dependencies including stable SSL libraries
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    openssl \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Create non-root user
RUN useradd -m -u 1000 repolens && \
    mkdir -p /app /data && \
    chown -R repolens:repolens /app /data

# Set working directory
WORKDIR /app

# Copy Python packages from builder (system-wide installation)
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY --chown=repolens:repolens . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

# Switch to non-root user
USER repolens

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
