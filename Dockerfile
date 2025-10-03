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

# Run the FastAPI application
CMD ["uvicorn", "kato.services.kato_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]