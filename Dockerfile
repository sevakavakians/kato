FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install FastAPI and Uvicorn
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    python-multipart==0.0.6 \
    websockets==12.0

# Install additional dependencies
RUN pip install --no-cache-dir \
    aioredis==2.0.1 \
    pymongo==4.5.0 \
    psutil==5.9.6

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