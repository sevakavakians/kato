# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. It processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency and traceability.

## Common Development Commands

### Building and Running
```bash
# Start KATO with vector database (recommended)
./kato-manager.sh start

# Build Docker image
./kato-manager.sh build

# Restart services
./kato-manager.sh restart

# Stop services
./kato-manager.sh stop

# Check status
./kato-manager.sh status

# View logs
docker logs kato-api-$(whoami)-1 --tail 20
```

### Testing
```bash
# Run all tests (recommended)
./run_tests.sh

# Run specific test categories
./run_tests_simple.sh unit      # Unit tests only
./run_tests_simple.sh integration # Integration tests
./run_tests_simple.sh api       # API tests

# Run single test file
python3 -m pytest tests/unit/test_memory_management.py -v

# Run specific test
python3 -m pytest tests/unit/test_memory_management.py::test_working_memory_operations -v

# Run with markers
python3 -m pytest -m "not slow" -v  # Skip slow tests
```

### Development and Debugging
```bash
# Update container without rebuild (hot reload)
./update_container.sh

# Check linting (if available)
# Note: No standard linting command found - ask user if needed

# Type checking (if available)  
# Note: No standard type checking command found - ask user if needed

# Debug ZMQ communication
docker exec kato-api-$(whoami)-1 python3 -c "import socket; s = socket.socket(); s.settimeout(1); result = s.connect_ex(('localhost', 5555)); print('ZMQ port 5555 is', 'open' if result == 0 else 'closed')"
```

## High-Level Architecture

### Distributed Processing Architecture
```
REST Client → REST Gateway (Port 8000) → ZMQ Server (Port 5555) → KATO Processor
                    ↓                           ↓                        ↓
              HTTP to ZMQ              ROUTER/DEALER Pattern      Working Memory
                                                                         ↓
                                                              Vector DB (Qdrant)
```

### Core Components

1. **REST Gateway** (`kato/workers/rest_gateway.py`)
   - FastAPI-based HTTP server on port 8000
   - Translates REST requests to ZMQ messages
   - Handles `/observe`, `/predict`, `/ping` endpoints

2. **ZMQ Server** (`kato/workers/zmq_server.py`, `zmq_pool_improved.py`)
   - High-performance message queue using ROUTER/DEALER pattern
   - Manages connection pooling and load balancing
   - Switchable implementations via `KATO_ZMQ_IMPLEMENTATION` env var

3. **KATO Processor** (`kato/workers/kato_processor.py`)
   - Core AI engine managing observations and predictions
   - Maintains working memory and long-term memory
   - Coordinates with vector database for similarity searches
   - Implements deterministic hashing for model identification

4. **Vector Database Layer** (`kato/storage/`)
   - Primary: Qdrant with HNSW indexing for 10-100x performance
   - Abstraction layer supports multiple backends
   - Redis caching for frequently accessed vectors
   - GPU acceleration and quantization support

### Memory Architecture

- **Working Memory**: Temporary storage for current observation sequences
- **Long-Term Memory**: Persistent storage with `MODEL|<sha1_hash>` patterns
- **Vector Storage**: Modern Qdrant database with collection per processor
- **Model Hashing**: SHA1-based deterministic model identification

### Key Behavioral Properties

1. **Alphanumeric Sorting**: Strings within events are sorted alphanumerically for consistency
2. **Temporal Segmentation**: Predictions structured as past/present/future
3. **Empty Event Handling**: Empty strings are filtered from observations
4. **Multi-Modal Processing**: Handles strings, vectors (768-dim), and emotional context
5. **Deterministic**: Same inputs always produce same outputs

## Testing Strategy

The codebase has 105+ tests with 100% pass rate. When adding new features:

1. **Unit Tests** (`tests/unit/`): Test individual components in isolation
2. **Integration Tests** (`tests/integration/`): Test end-to-end workflows
3. **API Tests** (`tests/api/`): Validate REST endpoints

Use existing fixtures from `tests/fixtures/kato_fixtures.py` for consistency.

## Configuration

### Environment Variables
- `MANIFEST`: JSON string for processor configuration
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `KATO_ZMQ_IMPLEMENTATION`: "simple" or "improved" (default: improved)
- `MONGO_BASE_URL`: MongoDB connection string
- `ZMQ_PORT`: ZeroMQ port (default: 5555)
- `REST_PORT`: REST API port (default: 8000)

### Multi-Instance Support
Use processor ID and name for multiple instances:
```bash
PROCESSOR_ID=p123 PROCESSOR_NAME=CustomProcessor ./kato-manager.sh start
```

## Recent Modernizations

- **Vector Database**: Migrated from linear search to Qdrant (10-100x faster)
- **ZMQ Architecture**: Migrated from gRPC for better multiprocessing support
- **Communication Pattern**: ROUTER/DEALER instead of REQ/REP for non-blocking ops
- **Technical Debt**: Major cleanup completed with comprehensive documentation

## Development Workflow

1. Make changes to source files in `kato/` directory
2. Use `./update_container.sh` for hot reload during development
3. Run relevant tests with `./run_tests_simple.sh <category>`
4. For production changes, rebuild with `./kato-manager.sh build`
5. Test full system with `./run_tests.sh` before committing

## Important Files and Locations

- Main processing logic: `kato/workers/kato_processor.py`
- REST API endpoints: `kato/workers/rest_gateway.py`
- Vector operations: `kato/storage/qdrant_manager.py`
- Model representations: `kato/representations/model.py`
- Test fixtures: `tests/fixtures/kato_fixtures.py`
- Management script: `kato-manager.sh`