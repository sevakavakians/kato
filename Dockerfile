FROM python:3.10-slim

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

# Run the FastAPI application with production settings
# --workers 1: Single worker for testing (multi-worker has 50% failure rate)
# --limit-concurrency 100: Max concurrent connections per worker
# --limit-max-requests 10000: Restart workers after N requests (prevents memory leaks)
# --timeout-keep-alive 5: Keep-alive timeout in seconds
# --backlog 2048: Maximum queued connections (OS-level)
# --access-log: Enable request logging
CMD ["uvicorn", "kato.services.kato_fastapi:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--limit-concurrency", "100", \
     "--limit-max-requests", "10000", \
     "--timeout-keep-alive", "5", \
     "--backlog", "2048", \
     "--access-log"]