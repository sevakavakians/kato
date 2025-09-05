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
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {"joy": 0.8},
    "unique_id": "obs-123"  # Optional unique identifier
  }'

# Learn pattern from current STM
curl -X POST http://localhost:8001/learn
# Returns: {"pattern_name": "PTRN|<hash>", "processor_id": "...", "message": "..."}

# Get predictions
curl -X GET http://localhost:8001/predictions
# Or with specific observation ID:
curl -X GET "http://localhost:8001/predictions?unique_id=obs-123"
```

## Core Concepts

KATO processes observations as **events** containing strings, vectors, and emotives. Each event is processed through:
- **Alphanumeric sorting** within events
- **Deterministic hashing** for patterns (PTRN|<sha1_hash>)
- **Temporal segmentation** in predictions
- **Empty event filtering**
- **Minimum requirement**: 2+ strings in STM for predictions (vectors contribute strings)

Learn more in [Core Concepts](docs/CONCEPTS.md).

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

KATO uses a simplified test architecture where tests run in local Python and connect to running services:

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
./run_tests.sh --no-start --no-stop

# Run specific test suite
./run_tests.sh --no-start --no-stop tests/tests/unit/
./run_tests.sh --no-start --no-stop tests/tests/integration/
./run_tests.sh --no-start --no-stop tests/tests/api/

# Run specific test file
./run_tests.sh --no-start --no-stop tests/tests/unit/test_sorting_behavior.py

# Run with verbose output
./run_tests.sh --no-start --no-stop -v tests/tests/unit/

# Run tests with fresh KATO (slower but cleaner)
./run_tests.sh  # Will start/stop KATO automatically
```

### Test Architecture
- **No Docker in Tests**: Tests run in local Python, connect to running KATO service
- **Automatic Isolation**: Each test gets unique processor_id for complete isolation
- **Fast Iteration**: Direct Python execution allows debugging with print/breakpoints
- **Parallel Safe**: Tests can run in parallel thanks to processor_id isolation

**Current Status**: 185 total tests (184 passing, 1 intentionally skipped) across unit, integration, API, and performance suites

See [Testing Guide](docs/TESTING.md) for complete details.

## Documentation

### 📚 Getting Started
- [Quick Start Guide](docs/GETTING_STARTED.md) - Get running in 5 minutes
- [API Reference](docs/API_REFERENCE.md) - Complete endpoint documentation
- [Configuration Guide](docs/CONFIGURATION.md) - All environment variables
- [Glossary](docs/GLOSSARY.md) - Terms and concepts defined
- [Multi-Instance Guide](docs/MULTI_INSTANCE_GUIDE.md) - Run multiple KATO processors
- [System Overview](docs/SYSTEM_OVERVIEW.md) - Understand the architecture
- [Core Concepts](docs/CONCEPTS.md) - Learn KATO's behavior

### 🚀 Deployment
- [Docker Guide](docs/deployment/DOCKER.md) - Container deployment
- [Configuration](docs/deployment/CONFIGURATION.md) - All parameters explained
- [Architecture](docs/deployment/ARCHITECTURE.md) - System design

### 🔧 Development
- [API Reference](docs/API_REFERENCE.md) - Complete endpoint documentation
- [Testing Guide](docs/TESTING.md) - Write and run tests
- [Contributing](docs/development/CONTRIBUTING.md) - Development guidelines

### 📊 Technical
- [Performance Guide](docs/technical/PERFORMANCE.md) - Optimization strategies
- [Troubleshooting](docs/technical/TROUBLESHOOTING.md) - Common issues
- [Prediction Object Reference](docs/technical/PREDICTION_OBJECT_REFERENCE.md) - Complete field documentation
- [Vector Architecture](docs/VECTOR_ARCHITECTURE_IMPLEMENTATION.md) - Modern vector database system
- [Breaking Changes](docs/BREAKING_CHANGES_VECTOR_ARCHITECTURE.md) - Vector migration guide
- [Known Issues](docs/KNOWN_ISSUES_AND_BUGS.md) - Current bugs and workarounds

### 📁 Documentation Structure

```
docs/
├── CONCEPTS.md              # Core behavior reference
├── GETTING_STARTED.md       # Quick start guide
├── MULTI_INSTANCE_GUIDE.md  # Multi-instance management
├── API_REFERENCE.md         # Complete API docs
├── SYSTEM_OVERVIEW.md       # End-to-end behavior
├── TESTING.md               # Complete testing guide
├── VECTOR_ARCHITECTURE_IMPLEMENTATION.md  # Vector DB system
├── VECTOR_MIGRATION_GUIDE.md              # Migration steps
├── VECTOR_TEST_RESULTS.md                 # Performance data
├── BREAKING_CHANGES_VECTOR_ARCHITECTURE.md # Breaking changes
├── KNOWN_ISSUES_AND_BUGS.md               # Current issues
├── deployment/
│   ├── ARCHITECTURE.md      # System design
│   ├── CONFIGURATION.md     # All parameters
│   └── DOCKER.md            # Container guide
├── development/
│   ├── CONTRIBUTING.md      # Dev guidelines
│   └── CHANGELOG.md         # Version history
└── technical/
    ├── PERFORMANCE.md       # Optimization guide
    ├── TROUBLESHOOTING.md   # Issue resolution
    └── PREDICTION_OBJECT_REFERENCE.md # Field documentation
```

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

#### Status
```http
GET /status
```
Returns detailed processor status including STM length and time counter.

#### Observe
```http
POST /observe
{
  "strings": ["string"],          # String symbols to observe
  "vectors": [[float]],            # Optional vector embeddings (768-dim)
  "emotives": {"key": float},      # Optional emotional/utility values
  "unique_id": "string"            # Optional unique identifier for tracking
}
```
Adds observation to short-term memory. Returns observation result with auto-learning status.

#### Get Short-Term Memory
```http
GET /stm
GET /short-term-memory  # Alias
```
Returns current short-term memory state as list of events.

#### Learn
```http
POST /learn
```
Learns pattern from current short-term memory. Returns pattern name as `PTRN|<hash>`.

#### Get Predictions
```http
GET /predictions
POST /predictions
GET /predictions?unique_id=<id>  # Get predictions for specific observation
```
Returns predictions based on current STM state or specific observation.

#### Clear STM
```http
POST /clear-stm
POST /clear-short-term-memory  # Alias
```
Clears short-term memory only.

#### Clear All Memory
```http
POST /clear-all
POST /clear-all-memory  # Alias
```
Clears all memory (STM and long-term patterns).

### Advanced Endpoints

#### Get Pattern
```http
GET /pattern/{pattern_id}
```
Retrieves specific pattern by ID (with or without PTRN| prefix).

#### Update Genes
```http
POST /genes/update
{
  "genes": {
    "recall_threshold": 0.5,
    "max_predictions": 100
  }
}
```
Updates processor configuration parameters (genes).

#### Get Gene
```http
GET /gene/{gene_name}
```
Retrieves current value of a specific gene.

#### Get Percept Data
```http
GET /percept-data
```
Returns last received observation data (input perception).

#### Get Cognition Data
```http
GET /cognition-data
```
Returns current cognitive state including predictions, STM, and emotives.

#### Get Metrics
```http
GET /metrics
```
Returns processor metrics including observation count, patterns learned, and uptime.

### WebSocket Endpoint
```http
WS /ws
```
WebSocket connection for real-time bidirectional communication.
Supported message types: observe, get_stm, get_predictions, learn, clear_stm, clear_all, ping.

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

See [Performance Guide](docs/technical/PERFORMANCE.md) for optimization.

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

See [Troubleshooting Guide](docs/technical/TROUBLESHOOTING.md) for more solutions.

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/development/CONTRIBUTING.md) for:
- Development setup
- Code guidelines
- Testing requirements
- Pull request process

## License

This project is licensed under the terms in the [LICENSE](LICENSE) file.

## Heritage

KATO is derived from the [GAIuS](https://medium.com/@sevakavakians/what-is-gaius-a-responsible-alternative-to-neural-network-artificial-intelligence-part-1-of-3-1f7bbe583a32) framework, retaining its transparent, symbolic, and physics-informed learning process while focusing on deterministic memory and abstraction.

Like GAIuS before it, KATO adheres to [ExCITE AI](https://medium.com/@sevakavakians/what-is-excite-ai-712afd372af4) principles.

## Recent Updates

### Major Architecture Migration (2025-09)
- **NEW: FastAPI Architecture** - Replaced REST/ZMQ with direct FastAPI embedding
- **Fixed STM State Persistence** - Resolved state management problems
- **Simplified Testing** - Local Python tests with automatic isolation
- **Better Performance** - Reduced latency by removing inter-process communication

### Bug Fixes (2025-09-01)
- **Fixed Division by Zero Errors**: Resolved edge cases in metric calculations when:
  - Pattern fragmentation equals -1
  - Total ensemble pattern frequencies equal 0 (when no patterns match)
  - State is empty in hamiltonian calculations
  - MongoDB metadata documents are missing
- **Improved Error Handling**: Errors now provide detailed context instead of being masked with defaults
- **Enhanced Recall Threshold**: Better handling of threshold=0.0 for comprehensive pattern matching

## Support

- 📖 [Documentation](docs/) - Complete documentation
- 🐛 [Issue Tracker](https://github.com/sevakavakians/kato/issues) - Report bugs
- 💬 [Discussions](https://github.com/sevakavakians/kato/discussions) - Ask questions

---

*Because in AI, memory without traceability or understanding is just confusion.*