# CLAUDE.md - AI Assistant Navigation Index

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📖 Documentation Navigation

**Start here**: See [docs/00-START-HERE.md](docs/00-START-HERE.md) for complete documentation index organized by role and audience.

### Quick Links by Task

- **Getting started with KATO**: [docs/users/quick-start.md](docs/users/quick-start.md)
- **Understanding architecture**: [docs/developers/architecture.md](docs/developers/architecture.md) + [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)
- **Deploying to production**: [docs/operations/docker-deployment.md](docs/operations/docker-deployment.md)
- **Understanding algorithms**: [docs/research/README.md](docs/research/README.md)
- **Integration patterns**: [docs/integration/README.md](docs/integration/README.md)
- **Release management**: [docs/maintenance/releasing.md](docs/maintenance/releasing.md)
- **API reference**: [docs/reference/api/](docs/reference/api/)
- **Configuration reference**: [docs/reference/configuration-vars.md](docs/reference/configuration-vars.md)

## Project Overview

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. It processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency and traceability.

**Core Concept**: **Patterns** - learned sequences (temporal) or profiles (non-temporal) that represent knowledge.

## Essential Development Commands

### Dependency Management
```bash
# After editing requirements.txt, regenerate lock file
pip-compile --output-file=requirements.lock requirements.txt
docker-compose build --no-cache kato
```

### Building and Running
```bash
./start.sh                    # Start all services
docker-compose down           # Stop services
docker-compose restart        # Restart services
docker-compose ps             # Check status
docker-compose logs kato      # View logs
```

### Service URLs
- **KATO**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MongoDB**: mongodb://localhost:27017
- **Qdrant**: http://localhost:6333
- **Redis**: redis://localhost:6379

### Testing
```bash
./start.sh  # Services must be running first!

# Run all tests
./run_tests.sh --no-start --no-stop

# Run specific test suites
./run_tests.sh --no-start --no-stop tests/tests/unit/
./run_tests.sh --no-start --no-stop tests/tests/integration/
./run_tests.sh --no-start --no-stop tests/tests/api/

# Direct pytest
python -m pytest tests/tests/unit/ -v
```

**Details**: See [docs/developers/testing.md](docs/developers/testing.md)

## Architecture Quick Reference

```
FastAPI Service (Port 8000)
    ↓
Session Manager (Redis)
    ↓
KatoProcessor (Per node_id)
    ↓
├─ MemoryManager (STM/LTM)
├─ PatternProcessor (Learning/Matching)
├─ VectorProcessor (Embeddings)
└─ ObservationProcessor (Input)
    ↓
Storage Layer
├─ MongoDB (Patterns)
├─ Qdrant (Vectors)
└─ Redis (Sessions/Cache)
```

**Complete Architecture**: See [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) and [docs/developers/architecture.md](docs/developers/architecture.md)

## Important Files and Locations

### API Layer
- `kato/api/endpoints/sessions.py` - Session-based API (primary)
- `kato/api/endpoints/kato_ops.py` - Utility endpoints

### Core Processing
- `kato/workers/kato_processor.py` - Main processing engine
- `kato/workers/pattern_processor.py` - Pattern learning/matching
- `kato/workers/observation_processor.py` - Input processing

### Storage & Search
- `kato/storage/qdrant_manager.py` - Vector operations
- `kato/searches/pattern_search.py` - Pattern matching
- `kato/sessions/session_manager.py` - Session management

### Configuration
- `kato/config/settings.py` - Environment-based configuration
- `kato/config/session_config.py` - Per-session configuration

### Testing
- `tests/tests/fixtures/kato_fixtures.py` - Test fixtures
- `./start.sh` - Service startup
- `./run_tests.sh` - Test runner

**Code Organization**: See [docs/developers/code-organization.md](docs/developers/code-organization.md)

## Configuration Quick Reference

### Key Environment Variables
- `PROCESSOR_ID`: Unique identifier (required)
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `MAX_PATTERN_LENGTH`: Auto-learn trigger (default: 0 = manual)
- `STM_MODE`: CLEAR or ROLLING (default: CLEAR)
- `RECALL_THRESHOLD`: 0.0-1.0 (default: 0.1)
- `SESSION_TTL`: Session timeout in seconds (default: 3600)
- `SESSION_AUTO_EXTEND`: Auto-extend TTL on access (default: true)

### Session Configuration
Update configuration per session via API:
```bash
POST /sessions/{session_id}/config
{
  "config": {
    "recall_threshold": 0.5,
    "max_predictions": 100,
    "use_token_matching": true
  }
}
```

**Complete Configuration**: See [docs/reference/configuration-vars.md](docs/reference/configuration-vars.md)

## Key Behavioral Properties (Quick Reference)

### Critical Rules
1. **Minimum Sequence Length**: 2+ strings total in STM required for predictions
2. **Alphanumeric Sorting**: Strings sorted within events (configurable)
3. **Deterministic**: Same inputs → same outputs (always)
4. **Session Isolation**: Each session has isolated STM, shared LTM per node_id
5. **Config-as-Parameter**: Configuration passed as parameters (not mutated)

### Pattern Matching Modes
- **Token-level** (default): EXACT difflib compatibility, 9x faster, use for tokenized text
- **Character-level**: Fuzzy string matching, 75x faster, use for document chunks only

**Details**: See [docs/research/pattern-matching.md](docs/research/pattern-matching.md)

### Prediction Structure
- **past**: Events before first match
- **present**: ALL events containing matches (complete events, not just matches)
- **future**: Events after last match
- **missing**: Event-structured list of unobserved symbols (aligned with present)
- **extras**: Event-structured list of unexpected symbols (aligned with STM)

**Details**: See [docs/research/predictive-information.md](docs/research/predictive-information.md)

### Multi-Modal Processing
- **Strings**: Discrete symbols
- **Vectors**: 768-dim embeddings → hash-based names (VCTR|hash)
- **Emotives**: Emotional context (-1 to +1), rolling window storage
- **Metadata**: Contextual tags, set-union accumulation

**Details**:
- Vectors: [docs/research/vector-embeddings.md](docs/research/vector-embeddings.md)
- Emotives: [docs/research/emotives-processing.md](docs/research/emotives-processing.md)
- Metadata: [docs/research/metadata-processing.md](docs/research/metadata-processing.md)

## Testing Architecture

### Test Isolation
- Each test gets unique `processor_id` for complete database isolation
- Format: `test_{test_name}_{timestamp}_{uuid}`
- Tests run in local Python, connect to Docker services
- Fast iteration - no container rebuilds for tests

### Test Organization
- `tests/tests/unit/` - Component tests
- `tests/tests/integration/` - End-to-end workflows
- `tests/tests/api/` - REST endpoint tests
- `tests/tests/performance/` - Stress tests

**Details**: See [docs/developers/testing.md](docs/developers/testing.md)

## Automated Planning System Protocol

### ⚠️ CRITICAL RULE: NEVER EDIT planning-docs/ FILES DIRECTLY ⚠️

**Claude Code's Role**:
- **READ-ONLY** access to planning documentation
- **TRIGGER** project-manager agent for ALL planning updates
- **EXECUTE** development tasks only

**Trigger project-manager agent when**:
- Task completion
- New tasks created
- Blocker encountered/resolved
- Architectural decision made
- Milestone reached

**Context Loading**:
1. Always read `planning-docs/README.md` first
2. Read `planning-docs/SESSION_STATE.md` for current task
3. Load additional context on-demand

**Details**: See section "Automated Planning System Protocol" in original CLAUDE.md (lines 901-972)

## Test Execution Protocol

### Local Testing (Recommended)
```bash
./start.sh  # Ensure services running
./run_tests.sh --no-start --no-stop
```

### test-analyst Agent (Only for Docker-based testing)
Use ONLY for:
- Tests requiring container rebuilds
- Complex test orchestration
- Performance benchmarking

**Details**: See [docs/developers/testing.md](docs/developers/testing.md)

## Container Manager Workflow Protocol

### When to Use
- **patch**: Bug fixes, security patches, performance improvements
- **minor**: New features, new endpoints, backward-compatible additions
- **major**: Breaking changes, API incompatibilities, required migrations

### Workflow
Claude Code automatically:
1. Analyzes git history and commit messages
2. Determines appropriate version bump (patch/minor/major)
3. Executes `./container-manager.sh [bump_type] "description"`
4. Builds and pushes container images to ghcr.io

**Details**: See [docs/maintenance/releasing.md](docs/maintenance/releasing.md)

## Agent Usage Summary

### Available Agents
1. **project-manager**: Planning documentation updates
2. **test-analyst**: Docker-based testing only
3. **general-purpose**: Complex research, version management

### Quick Decision Tree
- Updating planning docs? → project-manager
- Running Docker tests? → test-analyst
- Running local tests? → Do directly with `./run_tests.sh`
- Code ready to release? → Direct workflow (analyze + run container-manager.sh)
- Complex research? → general-purpose
- Everything else? → Do directly

## Common Development Workflow

1. Make changes to source files in `kato/`
2. Restart services: `docker-compose restart`
3. Run tests: `./run_tests.sh --no-start --no-stop`
4. Debug with print statements or debugger (tests run locally)
5. Commit changes when tests pass
6. Trigger project-manager agent to update planning docs

## Critical Reminders

- **ALWAYS** update `requirements.lock` after modifying `requirements.txt`
- **NEVER** edit `planning-docs/` files directly (use project-manager agent)
- **ALWAYS** rebuild KATO docker image after code updates: `docker-compose build --no-cache kato`
- **Services must be running** before tests: `./start.sh`
- **Each test needs unique processor_id** for isolation
- **Do NOT use MCPs** for this project

## Additional Documentation

### For Detailed Information, See:

**Users**:
- Quick Start: [docs/users/quick-start.md](docs/users/quick-start.md)
- API Reference: [docs/users/api-reference.md](docs/users/api-reference.md)
- Core Concepts: [docs/users/concepts.md](docs/users/concepts.md)

**Developers**:
- Contributing: [docs/developers/contributing.md](docs/developers/contributing.md)
- Architecture: [docs/developers/architecture.md](docs/developers/architecture.md)
- Testing: [docs/developers/testing.md](docs/developers/testing.md)

**Operations**:
- Deployment: [docs/operations/docker-deployment.md](docs/operations/docker-deployment.md)
- Configuration: [docs/operations/configuration.md](docs/operations/configuration.md)
- Monitoring: [docs/operations/monitoring.md](docs/operations/monitoring.md)

**Research**:
- Core Concepts: [docs/research/core-concepts.md](docs/research/core-concepts.md)
- Pattern Matching: [docs/research/pattern-matching.md](docs/research/pattern-matching.md)
- Predictive Information: [docs/research/predictive-information.md](docs/research/predictive-information.md)

**Integration**:
- Architecture Patterns: [docs/integration/architecture-patterns.md](docs/integration/architecture-patterns.md)
- Multi-Instance: [docs/integration/multi-instance.md](docs/integration/multi-instance.md)
- Hybrid Agents: [docs/integration/hybrid-agents.md](docs/integration/hybrid-agents.md)

**Maintenance**:
- Release Process: [docs/maintenance/releasing.md](docs/maintenance/releasing.md)
- Known Issues: [docs/maintenance/known-issues.md](docs/maintenance/known-issues.md)

**Reference**:
- API Reference: [docs/reference/api/](docs/reference/api/)
- Configuration Variables: [docs/reference/configuration-vars.md](docs/reference/configuration-vars.md)
- Glossary: [docs/reference/glossary.md](docs/reference/glossary.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
