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

### Testing (Container-Based - Preferred)
```bash
# Build test harness container (first time or after dependency changes)
./test-harness.sh build

# Run all tests in container (recommended)
./kato-manager.sh test
# OR directly:
./test-harness.sh test

# Run specific test suites
./test-harness.sh suite unit        # Unit tests only
./test-harness.sh suite integration # Integration tests
./test-harness.sh suite api        # API tests
./test-harness.sh suite performance # Performance tests
./test-harness.sh suite determinism # Determinism tests

# Run specific test path
./test-harness.sh test tests/tests/unit/test_memory_management.py

# Run with pytest options
./test-harness.sh test tests/ -v -x  # Verbose, stop on first failure

# Generate coverage report
./test-harness.sh report

# Interactive shell in test container (for debugging)
./test-harness.sh shell

# Development mode (live code updates)
./test-harness.sh dev tests/tests/unit/ -v
```

Note: The container-based approach ensures consistent test environment without requiring local Python dependencies.

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

- **Short-Term Memory (STM)**: Temporary storage for current observation sequences (formerly Working Memory)
- **Long-Term Memory**: Persistent storage with `MODEL|<sha1_hash>` patterns
- **Vector Storage**: Modern Qdrant database with collection per processor
- **Model Hashing**: SHA1-based deterministic model identification

### Key Behavioral Properties

1. **Minimum Sequence Length**: KATO requires at least 2 strings total in STM to generate predictions
   - Valid: `[['A', 'B']]` (2 strings in 1 event)
   - Valid: `[['A'], ['B']]` (2 strings across 2 events)
   - Valid: `[['A']] + vectors` (1 user string + vector strings like 'VECTOR|<hash>')
   - Invalid: `[['A']]` (only 1 string without vectors - no predictions generated)
2. **Alphanumeric Sorting**: Strings within events are sorted alphanumerically for consistency
3. **Temporal Segmentation**: Predictions structured as past/present/future
4. **Empty Event Handling**: Empty strings are filtered from observations
5. **Multi-Modal Processing**: Handles strings, vectors (768-dim), and emotional context
   - Vectors always produce name strings (e.g., 'VECTOR|<hash>') for STM
6. **Deterministic**: Same inputs always produce same outputs
7. **Variable Sequence Lengths**: Supports sequences of arbitrary length (2+ strings total)
   - Events can have varying numbers of symbols
   - Each prediction has unique missing/matches/extras fields based on partial matching

## Testing Strategy

The codebase has 128 tests with 100% pass rate and 0 warnings. Tests are organized under `tests/tests/`:

1. **Unit Tests** (`tests/tests/unit/`): 83 tests for individual components
2. **Integration Tests** (`tests/tests/integration/`): 19 tests for end-to-end workflows
3. **API Tests** (`tests/tests/api/`): 21 tests for REST endpoints
4. **Performance Tests** (`tests/tests/performance/`): 5 stress and performance tests

Use existing fixtures from `tests/tests/fixtures/kato_fixtures.py` for consistency.

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
3. Run relevant tests with `./test-harness.sh suite <category>` or `./kato-manager.sh test`
4. For production changes, rebuild with `./kato-manager.sh build`
5. Test full system with `./test-harness.sh test` before committing

## Important Files and Locations

- Main processing logic: `kato/workers/kato_processor.py`
- REST API endpoints: `kato/workers/rest_gateway.py`
- Vector operations: `kato/storage/qdrant_manager.py`
- Model representations: `kato/representations/model.py`
- Test fixtures: `tests/fixtures/kato_fixtures.py`
- Management script: `kato-manager.sh`

## Automated Planning System Protocol

### ⚠️ CRITICAL RULE: NEVER EDIT planning-docs/ FILES DIRECTLY ⚠️

### Role Separation
**Claude Code's Responsibility**: 
- **READ-ONLY** access to planning documentation for context
- **TRIGGER** project-manager agent for ALL documentation updates
- **EXECUTE** development tasks (code, tests, configs)

**Project-Manager's Responsibility**:
- **EXCLUSIVE WRITE ACCESS** to all planning-docs/ files
- Documentation archival and organization
- Pattern tracking and velocity calculations
- Time estimate refinements

### ❌ FORBIDDEN ACTIONS for Claude Code:
- Using Edit, Write, or MultiEdit tools on ANY file in planning-docs/
- Creating new files in planning-docs/
- Modifying SESSION_STATE.md, DAILY_BACKLOG.md, or any other planning files

### ✅ CORRECT WORKFLOW:
1. **READ** planning docs to understand current state
2. **EXECUTE** development tasks
3. **TRIGGER** project-manager with results for documentation updates

**VIOLATION CONSEQUENCE**: Direct edits to planning-docs/ will create conflicts and break the documentation system.

### Every Session Start:
1. READ `planning-docs/README.md` to understand the current system state
2. The README will guide you to the most relevant documents for immediate context
3. Only read additional documents when specifically needed for the current work

### Trigger Project-Manager When:
Use the Task tool with subagent_type="project-manager" when these events occur:
- **Task Completion** → Agent will update SESSION_STATE, archive work, refresh backlogs
- **New Tasks Created** → Agent will add to backlogs with time estimates
- **Priority Changes** → Agent will reorder backlogs and update dependencies
- **Blocker Encountered** → Agent will log blocker, suggest alternative tasks
- **Blocker Resolved** → Agent will update estimates, clear blocker status
- **Architectural Decision** → Agent will update DECISIONS.md and ARCHITECTURE.md
- **New Specifications** → Agent will parse into tasks, update scope
- **Context Switch** → Agent will create session log, update current state
- **Milestone Reached** → Agent will archive phase, update project overview

### Context Loading Strategy (Read-Only):
1. **Immediate Context** (Always Load):
   - `planning-docs/README.md` → Entry point and guide
   - `planning-docs/SESSION_STATE.md` → Current task and progress
   - `planning-docs/DAILY_BACKLOG.md` → Today's priorities
   - Latest session log in `planning-docs/sessions/` (if exists)

2. **On-Demand Context** (Load When Needed):
   - `planning-docs/PROJECT_OVERVIEW.md` → Project scope and tech stack
   - `planning-docs/ARCHITECTURE.md` → Technical decisions and structure
   - `planning-docs/SPRINT_BACKLOG.md` → Weekly planning and future work
   - `planning-docs/DECISIONS.md` → Historical architectural choices
   - `planning-docs/completed/` → Previous work for reference

### How to Trigger the Project-Manager:
```
Example: After completing a task
assistant: "I've finished implementing the OAuth2 authentication feature. Let me trigger the project-manager to update our documentation."
<uses Task tool with subagent_type="project-manager">

The project-manager will automatically:
- Update SESSION_STATE.md progress
- Archive the completed task
- Refresh the backlogs
- Calculate actual vs estimated time
- Log any patterns observed
```

## Test Execution Protocol

### ⚠️ CRITICAL RULE: USE test-analyst FOR ALL TESTING ⚠️

### When to Trigger test-analyst:
Use the Task tool with subagent_type="test-analyst" when:
- **After Code Changes** → To verify functionality and catch regressions
- **After Bug Fixes** → To confirm fixes work and don't break other tests
- **After Feature Implementation** → To ensure comprehensive testing
- **When Investigating Test Failures** → To get detailed analysis
- **For Performance Testing** → To benchmark and analyze performance
- **When User Requests Testing** → Any test-related request

### ❌ FORBIDDEN ACTIONS for Claude Code:
- Running `./test-harness.sh` directly via Bash tool
- Running `./kato-manager.sh test` directly via Bash tool  
- Running pytest commands directly
- Executing test scripts manually

### ✅ CORRECT WORKFLOW:
```
❌ WRONG: Bash("./test-harness.sh test")
❌ WRONG: Bash("./kato-manager.sh test")
❌ WRONG: Bash("python -m pytest tests/")

✅ RIGHT: Task tool with subagent_type="test-analyst"
```

### Example Usage:
```
assistant: "I've completed the bug fix. Let me use the test-analyst to verify all tests pass."
<uses Task tool with subagent_type="test-analyst">

The test-analyst will:
- Run all appropriate tests
- Analyze test results and failures
- Check code quality metrics
- Examine container logs if needed
- Produce detailed test documentation
```

## Agent Usage Summary

### Available Specialized Agents:
1. **project-manager**: ALL planning-docs/ updates and documentation
2. **test-analyst**: ALL test execution and analysis  
3. **general-purpose**: Complex multi-step research tasks
4. **statusline-setup**: Configure Claude Code status line

### Quick Decision Tree:
- Updating documentation? → project-manager
- Running tests? → test-analyst
- Complex research? → general-purpose
- Everything else? → Do it directly

### Common Mistakes to Avoid:
1. ❌ Editing planning-docs/ directly → ✅ Use project-manager
2. ❌ Running test-harness.sh directly → ✅ Use test-analyst
3. ❌ Running pytest directly → ✅ Use test-analyst
4. ❌ Running kato-manager.sh test → ✅ Use test-analyst