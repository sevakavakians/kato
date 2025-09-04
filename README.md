# KATO

**Knowledge Abstraction for Traceable Outcomes**

> *Transparent memory and abstraction for agentic AI systems — deterministic, explainable, and emotive-aware.*

![KATO Crystal](assets/kato-graphic.png "KATO crystal")

## What is KATO?

KATO is a specialized AI module that provides **deterministic memory, abstraction, and recall** for modern agentic AI systems. It learns patterns from observations and makes temporal predictions with complete transparency and traceability.

### Pattern-Based Learning

KATO uses **patterns** as its core learning concept:
- **Temporal Patterns**: Time-ordered patterns with temporal dependencies
- **Profile Patterns**: Collections without temporal ordering requirements

Every learned structure in KATO is identified by a unique hash: `PTRN|<sha1_hash>`

**Important**: Patterns require at least 2 strings total to generate predictions. When learning patterns, frequency starts at 1 and increments with each re-learning of the same pattern.

### Key Features

✨ **Deterministic Learning** - Same inputs always yield same outputs  
🔍 **Full Transparency** - All internal states and decisions are explainable  
🎯 **Temporal Predictions** - Sophisticated past/present/future segmentation  
🧠 **Multi-Modal Support** - Process text, vectors, and emotional context  
⚡ **High Performance** - FastAPI async architecture with embedded processors  
🔄 **Stateful Processing** - Maintains context across observations  
🚀 **Multi-Instance Support** - Run multiple processors with different configurations  
📊 **Instance Isolation** - Each processor_id has completely isolated databases  
🎪 **Vector Database** - Modern vector search with Qdrant (10-100x faster)  

### Example Architecture

![KATO Agent](assets/kato-agent.png "KATO agent")

Combining KATO with black box stochastic processes such as General Purpose Transformer (GPT) models, Large Language Models (LLMs), Small Language Models (SLMs), and GPT-based reasoning models provides a layer of governance and control. These stochastic machine learning models suffer from issues like hallucinations, inconsistent outputs, hidden biases, high training and operational costs, and no assurances for guardrails or remediation attempts.

KATO provides a deterministic machine learning algorithm that learns context + action + outcome patterns, effectively caching for reduced calls to expensive models. Additionally, it stores these patterns in a traceable database (typically MongoDB) allowing both real-time learning and updates. If an action taken by the agent needs to be corrected so that it isn't repeated given the same or similar context, the database can simply be edited with an alternative action.


## Prerequisites

### System Requirements
- Docker and Docker Compose
- Python 3.9+ (for local development)
- 4GB+ RAM recommended
- MongoDB (auto-started with Docker)
- Qdrant Vector Database (auto-started with Docker)

### Required Python Packages (for development)
```bash
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

## Quick Start

### 1. Clone and Build
```bash
# Clone repository
git clone https://github.com/your-org/kato.git
cd kato

# Build Docker image
./kato-manager.sh build
```

### 2. Start Services
```bash
# Start all services (MongoDB, Qdrant, and 3 KATO instances)
./kato-manager.sh start

# Services will be available at:
# - Primary KATO: http://localhost:8001
# - Testing KATO: http://localhost:8002
# - Analytics KATO: http://localhost:8003
# - MongoDB: mongodb://localhost:27017
# - Qdrant: http://localhost:6333
```

### 3. Verify Installation
```bash
# Check health of primary instance
curl http://localhost:8001/health

# Response:
# {"status": "healthy", "processor_id": "primary", "uptime": 123.45}

# Check API documentation
# Open in browser: http://localhost:8001/docs
```

### 4. Basic Usage
```bash
# Send observation to primary instance
curl -X POST http://localhost:8001/observe \
  -H "Content-Type: application/json" \
  -d '{
    "processor_id": "my-processor",
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {"joy": 0.8}
  }'

# Learn pattern
curl -X POST http://localhost:8001/learn \
  -H "Content-Type: application/json" \
  -d '{"processor_id": "my-processor"}'

# Get predictions
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{"processor_id": "my-processor"}'
```

## Service Management

### Starting and Stopping
```bash
# Start all services
./kato-manager.sh start

# Stop all services
./kato-manager.sh stop

# Restart services
./kato-manager.sh restart

# Check status
./kato-manager.sh status
```

### Health Monitoring
```bash
# Check individual service health
curl http://localhost:8001/health  # Primary
curl http://localhost:8002/health  # Testing
curl http://localhost:8003/health  # Analytics

# View logs
./kato-manager.sh logs          # All services
./kato-manager.sh logs primary  # Specific service
docker logs kato-primary --tail 50  # Direct Docker logs
```

## Testing

### Prerequisites for Testing
```bash
# Services must be running first
./kato-manager.sh start

# Set up Python environment (one-time setup)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

### Running Tests
```bash
# Run all tests (services must be running)
./run_simple_tests.sh --no-start --no-stop

# Run specific test suite
./run_simple_tests.sh --no-start --no-stop tests/tests/unit/
./run_simple_tests.sh --no-start --no-stop tests/tests/integration/
./run_simple_tests.sh --no-start --no-stop tests/tests/api/

# Run specific test file
./run_simple_tests.sh --no-start --no-stop tests/tests/unit/test_sorting_behavior.py

# Run with verbose output
./run_simple_tests.sh --no-start --no-stop -v tests/tests/unit/

# Run tests with fresh KATO (slower but cleaner)
./run_simple_tests.sh  # Will start/stop KATO automatically
```

### Test Architecture
- **No Docker in Tests**: Tests run in local Python, connect to running KATO service
- **Automatic Isolation**: Each test gets unique processor_id for complete isolation
- **Fast Iteration**: Direct Python execution allows debugging with print/breakpoints
- **Parallel Safe**: Tests can run in parallel thanks to processor_id isolation

## Architecture Overview

### FastAPI Architecture (Current)
KATO now uses a simplified FastAPI architecture with embedded processors:

```
Client Request → FastAPI Service (Port 8001-8003) → Embedded KATO Processor
                           ↓                                    ↓
                    Async Processing                    MongoDB & Qdrant
                           ↓                            (Isolated by processor_id)
                    JSON Response
```

**Key Improvements:**
- **Direct Embedding**: KATO processor runs in same process as API
- **No Connection Issues**: Eliminated state management problems
- **Better Performance**: No inter-process communication overhead
- **Simpler Debugging**: Single process, clear stack traces
- **Full Async Support**: FastAPI's async capabilities for high concurrency

### Database Isolation
Each processor_id maintains complete isolation:
- **MongoDB**: Database name = processor_id (e.g., `test_123.patterns_kb`)
- **Qdrant**: Collection name = `vectors_{processor_id}`
- **In-Memory**: Per-processor caches and state

## Configuration

### Environment Variables
Services can be configured via environment variables in `docker-compose.yml`:

```yaml
environment:
  - PROCESSOR_ID=primary           # Unique identifier
  - PROCESSOR_NAME=Primary          # Display name
  - MONGO_BASE_URL=mongodb://mongodb:27017
  - QDRANT_HOST=qdrant
  - QDRANT_PORT=6333
  - MAX_PATTERN_LENGTH=0           # 0 = manual learning only
  - PERSISTENCE=5                  # STM persistence
  - RECALL_THRESHOLD=0.1           # Pattern matching threshold
  - LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
```

### Multiple Configurations
The `docker-compose.yml` includes three pre-configured instances:
- **Primary** (8001): General use, manual learning
- **Testing** (8002): Debug logging, for development
- **Analytics** (8003): Auto-learn after 50 observations, higher recall threshold

## API Reference

### Core Endpoints

#### Health Check
```http
GET /health
```
Returns service health status and uptime.

#### Observe
```http
POST /observe
{
  "processor_id": "string",
  "strings": ["string"],
  "vectors": [[float]],
  "emotives": {"key": float}
}
```
Adds observation to short-term memory.

#### Learn
```http
POST /learn
{
  "processor_id": "string"
}
```
Learns pattern from current short-term memory.

#### Predict
```http
POST /predict
{
  "processor_id": "string",
  "recall_threshold": 0.1
}
```
Gets predictions based on current observations.

#### Clear Memory
```http
POST /clear-memory
{
  "processor_id": "string",
  "memory_type": "all|stm|ltm"
}
```
Clears specified memory type.

### Interactive Documentation
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## Performance

### Current Performance Metrics
- **Latency**: 1-5ms per observation
- **Throughput**: 5,000+ requests/second per instance
- **Memory**: 200MB-500MB per processor
- **Startup Time**: 2-3 seconds
- **Vector Search**: 10-100x faster with Qdrant

### Scaling
- **Vertical**: Increase resources for individual containers
- **Horizontal**: Run multiple KATO instances on different ports
- **Load Balancing**: Use nginx or similar for distributing requests

## Troubleshooting

### Common Issues

#### Services Won't Start
```bash
# Check if ports are in use
lsof -i :8001
lsof -i :27017
lsof -i :6333

# Clean restart
./kato-manager.sh stop
docker-compose down
docker-compose up -d
```

#### Tests Failing
```bash
# Ensure services are running
./kato-manager.sh status

# Check service health
curl http://localhost:8001/health

# Rebuild if needed
./kato-manager.sh build
./kato-manager.sh restart
```

#### Memory Issues
```bash
# Check Docker resources
docker system df
docker system prune -f

# Restart with fresh state
./kato-manager.sh stop
docker volume prune -f
./kato-manager.sh start
```

## Documentation

### 📚 Guides
- [API Reference](docs/API_REFERENCE.md) - Complete endpoint documentation
- [Core Concepts](docs/CONCEPTS.md) - KATO's behavior and patterns
- [Testing Guide](docs/TESTING.md) - Comprehensive testing documentation
- [Configuration Guide](docs/CONFIGURATION.md) - All parameters explained

### 🔧 Development
- [Contributing](docs/CONTRIBUTING.md) - Development guidelines
- [Architecture](docs/ARCHITECTURE.md) - System design details

## Recent Updates (2025-09)

### Major Architecture Migration
- **NEW: FastAPI Architecture** - Replaced REST/ZMQ with direct FastAPI embedding
- **Removed ZeroMQ Layer** - Eliminated connection pooling issues
- **Fixed STM State Persistence** - Resolved state management problems
- **Simplified Testing** - Local Python tests with automatic isolation
- **Better Performance** - Reduced latency by removing inter-process communication

### Bug Fixes
- Fixed empty STM issue where state was lost between requests
- Resolved processor isolation in tests
- Fixed MongoDB health check compatibility

## Support

- 📖 [Documentation](docs/) - Complete documentation
- 🐛 [Issue Tracker](https://github.com/sevakavakians/kato/issues) - Report bugs
- 💬 [Discussions](https://github.com/sevakavakians/kato/discussions) - Ask questions

---

*Because in AI, memory without traceability or understanding is just confusion.*