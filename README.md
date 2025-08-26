# KATO

**Knowledge Abstraction for Traceable Outcomes**

> *Transparent memory and abstraction for agentic AI systems — deterministic, explainable, and emotive-aware.*

![KATO Crystal](assets/kato-graphic.png "KATO crystal")

## What is KATO?

KATO is a specialized AI module that provides **deterministic memory, abstraction, and recall** for modern agentic AI systems. It learns sequences of observations, recognizes patterns, and makes temporal predictions with complete transparency and traceability.

### Key Features

✨ **Deterministic Learning** - Same inputs always yield same outputs  
🔍 **Full Transparency** - All internal states and decisions are explainable  
🎯 **Temporal Predictions** - Sophisticated past/present/future segmentation  
🧠 **Multi-Modal Support** - Process text, vectors, and emotional context  
⚡ **High Performance** - 10,000+ requests/second with ZeroMQ  
🔄 **Stateful Processing** - Maintains context across observations  

### Example Architecture

![KATO Agent](assets/kato-agent.png "KATO agent")

Combining KATO with black box stochastic processes such as General Purpose Transformer (GPT) models, Large Language Models (LLMs), Small Language Models (SLMs), and GPT-based reasoning models provides a layer of governance and control. These stochastic machine learning models suffer from issues like hallucinations, inconsistent outputs, hidden biases, high training and operational costs, and no assurances for guardrails or remediation attempts.

KATO provides a deterministic machine learning algorithm that learns context + action + outcome sequences, effectively caching for reduced calls to expensive models. Additionally, it stores these sequences in a traceable database (typically MongoDB) allowing both real-time learning and updates. If an action taken by the agent needs to be corrected so that it isn't repeated given the same or similar context, the database can simply be edited with an alternative action.


## Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/kato.git
cd kato

# Build and start
./kato-manager.sh build
./kato-manager.sh start

# Verify installation
curl http://localhost:8000/kato-api/ping
```

For detailed setup instructions, see [Getting Started](docs/GETTING_STARTED.md).

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

### 📁 Documentation Structure

```
docs/
├── CONCEPTS.md              # Core behavior reference
├── GETTING_STARTED.md       # Quick start guide
├── API_REFERENCE.md         # Complete API docs
├── SYSTEM_OVERVIEW.md       # End-to-end behavior
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
cd tests
./run_tests.sh              # Run all tests (~22 seconds)
./run_tests.sh --unit       # Unit tests only
./run_tests.sh --api        # API tests only
```

**Current Status**: ✅ All 105 tests passing (100% success rate)

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