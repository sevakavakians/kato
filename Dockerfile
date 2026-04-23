FROM python:3.10-slim

# Build arguments for version metadata
ARG VERSION=dev
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

# OCI-compliant image labels
LABEL org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="KATO" \
      org.opencontainers.image.description="Knowledge Abstraction for Traceable Outcomes - Deterministic memory and prediction system" \
      org.opencontainers.image.vendor="Intelligent Artifacts" \
      org.opencontainers.image.source="https://github.com/intelligent-artifacts/kato" \
      org.opencontainers.image.documentation="https://github.com/intelligent-artifacts/kato/blob/main/README.md" \
      org.opencontainers.image.licenses="MIT"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.lock .

# Install all dependencies from locked requirements for reproducible builds
RUN pip install --no-cache-dir -r requirements.lock

# Cache bust for code changes
ARG CACHE_BUST=7
RUN echo "Cache bust: $CACHE_BUST"

# Copy the KATO package
COPY kato/ ./kato/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose the port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Run the FastAPI application with production settings.
# KATO_WORKERS: uvicorn worker processes (default 4). Set via kato-manager.sh
#   --workers N, docker-compose env, .env, or shell env. Multi-worker is safe
#   because (a) sessions are externally stateless and independent, (b)
#   ClickHouse writes use server-side async_insert with wait=1 (no per-worker
#   buffer), and (c) pattern creation is gated by Redis SETNX.
# KATO_LIMIT_CONCURRENCY: max concurrent connections per worker (default 100).
# Shell form so env-vars expand; `exec` so uvicorn is PID 1 for signal handling.
CMD ["sh", "-c", "exec uvicorn kato.services.kato_fastapi:app \
     --host 0.0.0.0 --port 8000 \
     --workers ${KATO_WORKERS:-4} \
     --limit-concurrency ${KATO_LIMIT_CONCURRENCY:-100} \
     --timeout-keep-alive 5 \
     --timeout-graceful-shutdown 30 \
     --backlog 2048 \
     --access-log"]