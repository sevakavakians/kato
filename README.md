# KATO

**Knowledge Abstraction for Traceable Outcomes**

> *Transparent memory and abstraction for agentic AI systems — deterministic, explainable, and emotive-aware.*

🆕 **Latest Features**: Multi-user session isolation, guaranteed writes, Redis sessions, complete backwards compatibility

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
⚡ **High Performance** - 3.57x throughput, 72% latency reduction, comprehensive optimizations  
🔄 **Stateful Processing** - Maintains context across observations  
🎪 **Vector Database** - Modern vector search with Qdrant (10-100x faster)  
👥 **Multi-User Sessions** - Complete STM isolation per user session  
💾 **Write Guarantees** - MongoDB majority write concern prevents data loss  
🔐 **Session Management** - Redis-backed sessions with TTL and isolation  
📊 **Session Isolation** - Each session has completely isolated state  

### Example Architecture

![KATO Agent](assets/kato-agent.png "KATO agent")

Combining KATO with black box stochastic processes such as Generative Pre-trained Transformer (GPT) models, Large Language Models (LLMs), Small Language Models (SLMs), and GPT-based reasoning models provides a layer of governance and control. These stochastic machine learning models suffer from issues like hallucinations, inconsistent outputs, hidden biases, high training and operational costs, and no assurances for guardrails or remediation attempts.

KATO provides a deterministic machine learning algorithm that learns context + action + outcome patterns, effectively caching for reduced calls to expensive models. Additionally, it stores these patterns in a traceable database (typically MongoDB) allowing both real-time learning and updates. If an action taken by the agent needs to be corrected so that it isn't repeated given the same or similar context, the database can simply be edited with an alternative action.

## Performance Optimizations

KATO has been extensively optimized for production use with comprehensive performance enhancements:

### 🚀 Performance Metrics
- **3.57x throughput improvement** (from 57 to 204 observations/second)
- **72% latency reduction** (from 439ms to 123ms average)  
- **97% network overhead reduction** through batch optimization
- **Linear scaling** with batch size for predictable performance

### 🔧 Optimization Features
- **Bloom Filter Pre-screening**: O(1) pattern candidate filtering eliminates 99% of unnecessary computations
- **Redis Pattern Caching**: 80-90% cache hit rate for frequently accessed patterns
- **MongoDB Aggregation Pipelines**: Server-side filtering and sorting reduces data transfer by 60%
- **Connection Pool Optimization**: 60-80% reduction in connection overhead
- **Distributed STM Management**: Redis Streams for scalable state coordination
- **Async Parallel Processing**: Multi-core pattern matching with AsyncIO

### 📊 Monitoring Endpoints
Real-time performance monitoring available at:
- `/performance-metrics` - Complete system performance and database stats
- `/connection-pools` - Connection pool health and statistics  
- `/cache/stats` - Redis cache performance metrics
- `/distributed-stm/stats` - Distributed STM performance monitoring

### 📈 Benchmarking Results
| Batch Size | Throughput (obs/sec) | Latency (ms) | Improvement |
|------------|---------------------|---------------|-------------|
| 10 obs     | 203.71 vs 57.00     | 122.73 vs 438.62 | **3.57x** |
| 50 obs     | 406.50 vs 114.29    | 49.09 vs 175.32  | **3.56x** |
| 100 obs    | 658.68 vs 185.19    | 30.35 vs 108.11  | **3.56x** |

See `docs/archive/optimizations/` for detailed benchmarks and implementation details.

## Prerequisites

### System Requirements
- Docker and Docker Compose
- Python 3.9+ (for local development)
- 4GB+ RAM recommended
- MongoDB (auto-started with Docker)
- Qdrant Vector Database (auto-started with Docker)
- Redis (auto-started with Docker)

### Required Python Packages (for development)
```bash
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

## Installation Options

### Option 1: Using Pre-Built Container Images (Recommended)

KATO provides official pre-built container images hosted on GitHub Container Registry. This is the fastest way to get started.

#### Available Image Tags

| Tag | Description | Use Case |
|-----|-------------|----------|
| `2.0.0` | Specific version (immutable) | Production - pin to exact version |
| `2.0` | Latest patch for 2.0.x | Auto-receive security/bug fixes |
| `2` | Latest minor for 2.x | Track major version |
| `latest` | Latest stable release | Development and testing |

#### Pull Pre-Built Image

```bash
# Recommended for production - pin to specific version
docker pull ghcr.io/sevakavakians/kato:2.0.0

# Auto-receive patch updates (security fixes, bug fixes)
docker pull ghcr.io/sevakavakians/kato:2.0

# Always use latest stable (for development)
docker pull ghcr.io/sevakavakians/kato:latest
```

#### Use with Docker Compose

Modify your `docker-compose.yml` to use pre-built images:

```yaml
services:
  kato:
    image: ghcr.io/sevakavakians/kato:2.0.0  # Use pre-built image
    # Remove 'build' section
    container_name: kato
    environment:
      - SERVICE_NAME=kato
      # ... rest of environment variables
```

See the [Standalone Deployment Guide](deployment/README.md) for complete instructions on using pre-built images.

### Option 2: Build from Source

If you need to modify the code or contribute to development, build from source.

## Quick Start

### 1. Clone Repository
```bash
# Clone repository
git clone https://github.com/your-org/kato.git
cd kato
```

### 2. Start Services
```bash
# Start all services (includes MongoDB, Qdrant, Redis, KATO)
./start.sh

# Services will be available at:
# - KATO Service: http://localhost:8000
# - MongoDB: mongodb://localhost:27017
# - Qdrant: http://localhost:6333
# - Redis: redis://localhost:6379
```

### 3. Verify Installation
```bash
# Check health
curl http://localhost:8000/health

# Response:
# {"status": "healthy", "session_id": "default", "uptime": 123.45}

# Quick test of basic functionality
./run_tests.sh --no-start --no-stop tests/tests/api/test_fastapi_endpoints.py::test_health_endpoint -v

# Check API documentation
# Open in browser: http://localhost:8000/docs
```

### 4. Basic Usage

#### Option A: Using Sessions (Recommended)
```bash
# Create a session for node isolation
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "alice"}' | jq -r '.session_id')

# Observe in isolated session
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"]}'

# Get session's isolated STM
curl http://localhost:8000/sessions/$SESSION/stm
```

**💾 Data Persistence Note:**
- Your `node_id` ("alice") is your **persistent identifier** - using the same `node_id` later will reconnect to all trained patterns
- Sessions (STM, emotives) are temporary and expire, but learned patterns in MongoDB persist forever
- See [Database Persistence Guide](docs/users/database-persistence.md) for complete details

#### Option B: Default Session API (backwards compatible)
```bash
# Send observation (backward compatible)
curl -X POST http://localhost:8000/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {"joy": 0.8},
    "unique_id": "obs-123"  # Optional unique identifier
  }'

# Learn pattern from current STM
curl -X POST http://localhost:8000/learn
# Returns: {"pattern_name": "PTRN|<hash>", "session_id": "...", "message": "..."}

# Get predictions
curl -X GET http://localhost:8000/predictions
# Or with specific observation ID:
curl -X GET "http://localhost:8000/predictions?unique_id=obs-123"
```

## Core Concepts

KATO processes observations as **events** containing strings, vectors, and emotives. Each event is processed through:
- **Alphanumeric sorting** within events
- **Deterministic hashing** for patterns (PTRN|<sha1_hash>)
- **Temporal segmentation** in predictions
- **Empty event filtering**
- **Minimum requirement**: 2+ strings in STM for predictions (vectors contribute strings)

Learn more in [Core Concepts](docs/developers/concepts.md) or [User Guide](docs/users/concepts.md).

## Service Management

### Starting and Stopping
```bash
# Start all services
./start.sh

# Stop all services
docker-compose down

# Restart services
docker-compose restart

# Check status
docker-compose ps
```

### Health Monitoring
```bash
# Check service health
curl http://localhost:8000/health

# View logs
docker-compose logs                # All services
docker-compose logs kato           # KATO service
docker logs kato --tail 50         # Direct Docker logs
```

## Testing

KATO uses a simplified test architecture where tests run in local Python and connect to running services:

### Prerequisites for Testing
```bash
# Services must be running first
./start.sh

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
./run_tests.sh  # Will start/stop services automatically
```

### Test Architecture
- **No Docker in Tests**: Tests run in local Python, connect to running KATO service
- **Automatic Isolation**: Each test gets unique processor_id for complete isolation
- **Fast Iteration**: Direct Python execution allows debugging with print/breakpoints
- **Parallel Safe**: Tests can run in parallel thanks to processor_id isolation

**Current Status**: 185 total tests (184 passing, 1 intentionally skipped) across unit, integration, API, and performance suites

See [Testing Guide](docs/developers/testing.md) for complete details.

## Documentation

### 📚 Getting Started
- [Quick Start Guide](docs/users/quick-start.md) - Get running in 5 minutes
- [API Reference](docs/users/api-reference.md) - Complete endpoint documentation
- [Configuration Management](docs/developers/configuration-management.md) - Comprehensive configuration system guide
- [Configuration Guide](docs/operations/configuration.md) - All environment variables
- [Glossary](docs/reference/glossary.md) - Terms and concepts defined
- [Multi-Instance Guide](docs/operations/multi-instance.md) - Run multiple KATO processors
- [Network Topology Patterns](docs/operations/network-topology.md) - Connect instances in various topologies
- [User Guide](docs/users/concepts.md) - Understand the architecture and usage
- [Developer Concepts](docs/developers/concepts.md) - Learn KATO's internal behavior

### 🚀 Deployment
- [Docker Guide](docs/deployment/DOCKER.md) - Container deployment
- [Configuration](docs/deployment/CONFIGURATION.md) - All parameters explained
- [Architecture](docs/deployment/ARCHITECTURE.md) - System design
- [Production Scale Migration Plan (PSMP)](docs/deployment/PRODUCTION_SCALE_MIGRATION_PLAN.md) - Future scaling strategy for production workloads

### 🔧 Development
- [API Reference](docs/users/api-reference.md) - Complete endpoint documentation
- [Testing Guide](docs/developers/testing.md) - Write and run tests
- [Contributing](docs/development/CONTRIBUTING.md) - Development guidelines

### 📊 Technical
- [Performance Guide](docs/technical/PERFORMANCE.md) - Optimization strategies
- [Troubleshooting](docs/technical/TROUBLESHOOTING.md) - Common issues
- [Prediction Object Reference](docs/technical/PREDICTION_OBJECT_REFERENCE.md) - Complete field documentation
- [Vector Architecture](docs/VECTOR_ARCHITECTURE_IMPLEMENTATION.md) - Modern vector database system
- [Breaking Changes](docs/BREAKING_CHANGES_VECTOR_ARCHITECTURE.md) - Vector migration guide
- [Known Issues](docs/maintenance/known-issues.md) - Current bugs and workarounds

### 📁 Documentation Structure

```
docs/
├── 00-START-HERE.md         # 📍 Start here - Central navigation hub
├── users/                   # 👤 End user documentation
│   ├── quick-start.md       # 5-minute quick start
│   ├── api-reference.md     # Complete API docs
│   ├── database-persistence.md # Data persistence
│   ├── concepts.md          # User-facing concepts
│   └── migration-guides/    # Version migration guides
├── developers/              # 💻 Core contributor documentation
│   ├── testing.md           # Complete testing guide
│   ├── concepts.md          # Internal concepts
│   └── configuration-management.md # Config system
├── operations/              # 🔧 DevOps and deployment
│   ├── configuration.md     # All parameters
│   ├── container-deployment.md # Container management
│   ├── multi-instance.md    # Multi-instance setup
│   └── network-topology.md  # Network patterns
├── research/                # 🔬 Algorithm and theory
│   ├── pattern-matching.md  # Pattern algorithms
│   ├── predictive-information.md # Prediction theory
│   ├── emotives-processing.md # Emotional context
│   └── metadata-processing.md # Metadata handling
├── integration/             # 🔌 Integration patterns
│   ├── hybrid-agents-analysis.md # LLM integration
│   └── websocket-integration.md # WebSocket patterns
├── maintenance/             # 🛠️ Project maintenance
│   └── known-issues.md      # Current bugs/workarounds
├── reference/               # 📖 Quick reference
│   └── glossary.md          # Terms and definitions
├── archive/                 # 📦 Historical documentation
│   ├── optimizations/       # Past optimization work
│   └── investigations/      # Research archives
├── deployment/              # Legacy deployment docs
│   ├── ARCHITECTURE.md
│   ├── CONFIGURATION.md
│   └── DOCKER.md
├── development/             # Legacy development docs
│   └── CONTRIBUTING.md
└── technical/               # Legacy technical docs
    ├── PERFORMANCE.md
    ├── TROUBLESHOOTING.md
    └── PREDICTION_OBJECT_REFERENCE.md
```

## Architecture Overview

### FastAPI Architecture (Current)
KATO uses a simplified FastAPI architecture with embedded processors:

```
Client Request → FastAPI Service (Port 8000) → Embedded KATO Processor
                           ↓                                    ↓
                    Async Processing              MongoDB, Qdrant & Redis
                           ↓                       (Isolated by session_id)
                    JSON Response
```

**Key Improvements:**
- **Direct Embedding**: KATO processor runs in same process as API
- **No Connection Issues**: Eliminated state management problems
- **Better Performance**: No inter-process communication overhead
- **Simpler Debugging**: Single process, clear stack traces
- **Full Async Support**: FastAPI's async capabilities for high concurrency

### Session Isolation
Each session maintains complete isolation:
- **Redis**: Session state isolated by session_id
- **MongoDB**: Patterns isolated by session context
- **Qdrant**: Vectors isolated by session collection
- **In-Memory**: Per-session caches and state

## Configuration

KATO uses environment variables for configuration with Pydantic-based validation.

### Key Configuration Parameters

```bash
# Database
MONGO_BASE_URL="mongodb://localhost:27017"
QDRANT_HOST="localhost"
REDIS_URL="redis://localhost:6379/0"

# Learning
MAX_PATTERN_LENGTH=0        # Auto-learn after N observations (0=manual)
RECALL_THRESHOLD=0.1        # Pattern matching threshold (0.0-1.0)
PERSISTENCE=5               # Emotive value window size
STM_MODE="CLEAR"            # STM mode after auto-learn (CLEAR/ROLLING)

# Processing
MAX_PREDICTIONS=100         # Maximum predictions to return
PROCESS_PREDICTIONS=true    # Enable prediction processing
RANK_SORT_ALGO="potential"  # Prediction ranking metric

# Sessions
SESSION_TTL=3600            # Session time-to-live (seconds)
SESSION_AUTO_EXTEND=true    # Auto-extend TTL on access

# API
LOG_LEVEL="INFO"            # Logging level
PORT=8000                   # API port
```

### Session Configuration

Each session can have independent configuration:

```bash
# Update session config
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"recall_threshold": 0.5, "max_predictions": 50}}'
```

For complete configuration details, see [Configuration Guide](docs/operations/configuration.md).

## API Reference

### Quick Start

> **⚠️ All operations require session-based endpoints** (Phase 3 migration complete).

```bash
# 1. Create session
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "user_alice"}'

# 2. Observe
curl -X POST http://localhost:8000/sessions/{session_id}/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"]}'

# 3. Learn pattern
curl -X POST http://localhost:8000/sessions/{session_id}/learn

# 4. Get predictions
curl http://localhost:8000/sessions/{session_id}/predictions
```

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sessions` | POST | Create new session |
| `/sessions/{id}/observe` | POST | Add observation |
| `/sessions/{id}/learn` | POST | Learn pattern |
| `/sessions/{id}/predictions` | GET | Get predictions |
| `/sessions/{id}/stm` | GET | View STM |
| `/sessions/{id}/config` | POST | Update config |
| `/health` | GET | Health check |
| `/metrics` | GET | Performance metrics |

**Full Documentation:**
- API Reference: [docs/users/api-reference.md](docs/users/api-reference.md)
- Interactive Docs: http://localhost:8000/docs

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
lsof -i :8000
lsof -i :27017
lsof -i :6333
lsof -i :6379

# Clean restart
docker-compose down
docker-compose up -d
```

#### Tests Failing
```bash
# Ensure services are running
docker-compose ps

# Check service health
curl http://localhost:8000/health

# Restart if needed
docker-compose restart
```

#### Memory Issues
```bash
# Check Docker resources
docker system df
docker system prune -f

# Restart with fresh state
docker-compose down
docker volume prune -f
./start.sh
```

#### MongoDB Init Container Exits After Startup
**This is expected behavior.** The `mongodb-init` container is designed to:
1. Start up when MongoDB is ready
2. Initialize the MongoDB replica set configuration
3. Exit successfully (with status code 0)
4. Remain in "Exited" state

This is an initialization container that only needs to run once. You can verify it completed successfully:
```bash
# Check exit status (should show "Exited (0)")
docker ps -a | grep mongodb-init

# View initialization logs
docker logs kato-mongodb-init
```

The main MongoDB container (`kato-mongodb`) will continue running normally. Only the init container stops after completing its setup task.

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
  - State is empty in normalized entropy calculations
  - MongoDB metadata documents are missing
- **Improved Error Handling**: Errors now provide detailed context instead of being masked with defaults
- **Enhanced Recall Threshold**: Better handling of threshold=0.0 for comprehensive pattern matching

## Support

- 📖 [Documentation](docs/) - Complete documentation
- 🐛 [Issue Tracker](https://github.com/sevakavakians/kato/issues) - Report bugs
- 💬 [Discussions](https://github.com/sevakavakians/kato/discussions) - Ask questions

---

*Because in AI, memory without traceability or understanding is just confusion.*
