FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the gateway application
COPY gateway/ ./gateway/
COPY run_gateway.py .

# Copy and regenerate protobuf files
COPY kato_proc.proto ./
RUN pip install grpcio-tools && \
    python -m grpc_tools.protoc \
    --proto_path=. \
    --python_out=. \
    --grpc_python_out=. \
    kato_proc.proto

# Expose REST port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Run the gateway
CMD ["python", "run_gateway.py"]