# KATO

**Knowledge Abstraction for Traceable Outcomes**

> *Transparent memory and abstraction for agentic AI systems — deterministic, explainable, and emotive-aware.*

![KATO Crystal](assets/kato-graphic.png "KATO crystal")

## What is KATO?

KATO is a specialized AI module that provides **deterministic memory, abstraction, and recall** for modern agentic AI systems. It learns patterns from observations and makes temporal predictions with complete transparency and traceability.

### Pattern-Based Learning

KATO uses **patterns** as its core learning concept:
- **Temporal Patterns**: Time-ordered sequences with temporal dependencies
- **Profile Patterns**: Collections without temporal ordering requirements

Every learned structure in KATO is identified by a unique hash: `PTRN|<sha1_hash>`

### Key Features

✨ **Deterministic Learning** - Same inputs always yield same outputs  
🔍 **Full Transparency** - All internal states and decisions are explainable  
🎯 **Temporal Predictions** - Sophisticated past/present/future segmentation  
🧠 **Multi-Modal Support** - Process text, vectors, and emotional context  
⚡ **High Performance** - 10,000+ requests/second with ZeroMQ  
🔄 **Stateful Processing** - Maintains context across observations  
🚀 **Multi-Instance Support** - Run multiple processors with different configurations  
📊 **Instance Management** - Built-in registry and management tools  
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
- MongoDB (auto-started)
- **Qdrant Vector Database** (auto-started)

### Required Python Packages
```bash
pip install qdrant-client>=1.7.0 redis>=4.5.0 aiofiles>=23.0.0
```

## Quick Start

### Single Instance
```bash
# Clone repository
git clone https://github.com/your-org/kato.git
cd kato

# Build and start (includes vector database)
./kato-manager.sh build
./kato-manager.sh start

# Verify installation
curl http://localhost:8000/kato-api/ping
```

### Vector Database
KATO now uses Qdrant for high-performance vector operations:
- **Automatic startup** with KATO
- **10-100x faster** than previous implementation
- **Port 6333** (Qdrant REST API)
- **Port 6334** (Qdrant gRPC)

### Multiple Instances
```bash
# Start multiple KATO instances with different configurations
./kato-manager.sh start --id processor-1 --name "Main" --port 8001
./kato-manager.sh start --id processor-2 --name "Secondary" --port 8002 --max-predictions 200

# List all instances
./kato-manager.sh list

# Access different instances
curl http://localhost:8001/processor-1/ping
curl http://localhost:8002/processor-2/ping

# Stop instances (removes containers)
./kato-manager.sh stop processor-1        # Stop by ID
./kato-manager.sh stop "Main"              # Stop by name
./kato-manager.sh stop --all --with-mongo  # Stop everything
```

For detailed setup instructions, see [Getting Started](docs/GETTING_STARTED.md).
For multi-instance management, see [Multi-Instance Guide](docs/MULTI_INSTANCE_GUIDE.md).

## Core Concepts

KATO processes observations as **events** containing strings, vectors, and emotives:

```python
# Send observation
curl -X POST http://localhost:8000/p46b6b076c/observe \
  -d '{"strings": ["hello", "world"], "vectors": [], "emotives": {"joy": 0.8}}'

# Learn sequence
curl -X POST http://localhost:8000/p46b6b076c/learn

# Get predictions
curl http://localhost:8000/p46b6b076c/predictions
```

Key behaviors:
- **Alphanumeric sorting** within events
- **Deterministic hashing** for models (MODEL|hash)
- **Temporal segmentation** in predictions
- **Empty event filtering**

Learn more in [Core Concepts](docs/CONCEPTS.md).

## Documentation

### 📚 Getting Started
- [Quick Start Guide](docs/GETTING_STARTED.md) - Get running in 5 minutes
- [Multi-Instance Guide](docs/MULTI_INSTANCE_GUIDE.md) - Run multiple KATO processors
- [System Overview](docs/SYSTEM_OVERVIEW.md) - Understand the architecture
- [Core Concepts](docs/CONCEPTS.md) - Learn KATO's behavior

### 🚀 Deployment
- [Docker Guide](docs/deployment/DOCKER.md) - Container deployment
- [Configuration](docs/deployment/CONFIGURATION.md) - All parameters explained
- [Architecture](docs/deployment/ARCHITECTURE.md) - System design

### 🔧 Development
- [API Reference](docs/API_REFERENCE.md) - Complete endpoint documentation
- [Testing Guide](docs/development/TESTING.md) - Write and run tests
- [Contributing](docs/development/CONTRIBUTING.md) - Development guidelines

### 📊 Technical
- [Performance Guide](docs/technical/PERFORMANCE.md) - Optimization strategies
- [Troubleshooting](docs/technical/TROUBLESHOOTING.md) - Common issues
- [ZeroMQ Architecture](docs/technical/ZEROMQ_ARCHITECTURE.md) - Protocol details
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
│   ├── TESTING.md           # Test documentation
│   ├── CONTRIBUTING.md      # Dev guidelines
│   └── CHANGELOG.md         # Version history
└── technical/
    ├── PERFORMANCE.md       # Optimization guide
    ├── TROUBLESHOOTING.md   # Issue resolution
    ├── ZEROMQ_ARCHITECTURE.md # Protocol details
    └── PREDICTION_OBJECT_REFERENCE.md # Field documentation
```

## Testing

KATO includes comprehensive tests covering all functionality:

```bash
# Build test harness (first time or after dependency changes)
./test-harness.sh build

# Run all tests in container (recommended)
./kato-manager.sh test
# OR directly:
./test-harness.sh test

# Run specific test suites
./test-harness.sh suite unit        # Unit tests only
./test-harness.sh suite api         # API tests only
./test-harness.sh suite integration # Integration tests
```

**Current Status**: ✅ All 128 tests passing (100% success rate)

See [Testing Guide](docs/development/TESTING.md) for details.

## Performance

- **Latency**: 1-5ms per observation
- **Throughput**: 10,000+ requests/second
- **Memory**: 500MB-2GB typical usage
- **Scaling**: Horizontal via multiple instances

See [Performance Guide](docs/technical/PERFORMANCE.md) for optimization.

## Architecture

KATO uses a distributed architecture with ZeroMQ ROUTER/DEALER pattern for high-performance, non-blocking communication:

```
REST Client → REST Gateway (Port 8000) → ZeroMQ ROUTER/DEALER (Port 5555) → KATO Processor
```

**Key Features:**
- **ROUTER/DEALER Pattern**: Non-blocking, concurrent request handling (improved over REQ/REP)
- **Connection Pooling**: Efficient connection reuse reduces overhead
- **Heartbeat Mechanism**: 30-second intervals ensure connection health
- **Automatic Recovery**: Resilient to network issues and timeouts

See [Architecture Documentation](docs/deployment/ARCHITECTURE.md) for details.

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

## Support

- 📖 [Documentation](docs/) - Complete documentation
- 🐛 [Issue Tracker](https://github.com/your-org/kato/issues) - Report bugs
- 💬 [Discussions](https://github.com/your-org/kato/discussions) - Ask questions

---

*Because in AI, memory without traceability or understanding is just confusion.*