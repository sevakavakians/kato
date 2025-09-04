# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. It processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency and traceability.

## Pattern Terminology

**Pattern** is the core concept in KATO that encompasses:
- **Temporal Patterns (Sequences)**: Patterns with temporal dependency and ordering sensitivity
- **Profile Patterns**: Patterns without temporal dependency or ordering requirements

All learned structures in KATO are patterns, whether they represent time-ordered sequences or unordered profiles.

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

### Testing (Local Python)
```bash
# Set up virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Run all tests
./run_simple_tests.sh

# Run specific test categories
./run_simple_tests.sh tests/tests/unit/        # Unit tests only
./run_simple_tests.sh tests/tests/integration/ # Integration tests
./run_simple_tests.sh tests/tests/api/        # API tests

# Run specific test file
./run_simple_tests.sh tests/tests/unit/test_observations.py

# Run with options
./run_simple_tests.sh -v                      # Verbose output
./run_simple_tests.sh --no-start              # Use existing KATO instance
./run_simple_tests.sh --no-stop               # Keep KATO running after tests

# Run tests directly with pytest
source venv/bin/activate
python -m pytest tests/tests/unit/ -v --tb=short
```

**Key Features:**
- Simple local Python testing without containers
- Direct debugging with print statements and breakpoints
- Fast iteration - no container builds
- Each test gets a unique processor_id for isolation
- Clear error messages and stack traces

### Development and Debugging
```bash
# Check linting (if available)
# Note: No standard linting command found - ask user if needed

# Type checking (if available)  
# Note: No standard type checking command found - ask user if needed

# Debug KATO API
curl http://localhost:8000/kato-api/ping

# Check ZMQ communication
python3 -c "import socket; s = socket.socket(); s.settimeout(1); result = s.connect_ex(('localhost', 5555)); print('ZMQ port 5555 is', 'open' if result == 0 else 'closed')"
```

## High-Level Architecture

### Distributed Processing Architecture
```
REST Client → REST Gateway (Port 8000) → ZMQ Server (Port 5555) → KATO Processor
                    ↓                           ↓                        ↓
              HTTP to ZMQ              ROUTER/DEALER Pattern      Short-Term Memory
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
   - Maintains short-term memory and long-term memory
   - Coordinates with vector database for similarity searches
   - Implements deterministic hashing for model identification

4. **Vector Database Layer** (`kato/storage/`)
   - Primary: Qdrant with HNSW indexing for 10-100x performance
   - Abstraction layer supports multiple backends
   - Redis caching for frequently accessed vectors
   - GPU acceleration and quantization support

### Memory Architecture

- **Short-Term Memory (STM)**: Temporary storage for current observation sequences
- **Long-Term Memory**: Persistent storage with `PTRN|<sha1_hash>` identifiers
- **Vector Storage**: Modern Qdrant database with collection per processor
- **Pattern Hashing**: SHA1-based deterministic pattern identification

### MongoDB Pattern Storage

- **Unique Indexing**: Patterns indexed by SHA1 hash of pattern data
- **Duplicate Prevention**: Uses `update_one` with `upsert=True` to prevent duplicates
- **Frequency Tracking**: Each re-learning of same pattern increments frequency counter
  - Minimum frequency = 1 (pattern must be learned at least once to exist)
  - Frequency increments each time the same pattern is re-learned
- **Pattern Naming**: `PTRN|<sha1_hash>` where hash uniquely identifies the pattern
- **Storage Guarantee**: Only one record per unique pattern in MongoDB

### Key Behavioral Properties

1. **Minimum Sequence Length**: KATO requires at least 2 strings total in STM to generate predictions
   - Valid: `[['A', 'B']]` (2 strings in 1 event)
   - Valid: `[['A'], ['B']]` (2 strings across 2 events)
   - Valid: `[['A']] + vectors` (1 user string + vector strings like 'VECTOR|<hash>')
   - Invalid: `[['A']]` (only 1 string without vectors - no predictions generated)
2. **Alphanumeric Sorting**: Strings within events are sorted alphanumerically for consistency
3. **Temporal Segmentation**: Predictions structured as past/present/future
   - **Past**: Events before the first matching event
   - **Present**: ALL events containing matching symbols from the observed state (from first to last match)
     - Includes ALL symbols within those events, even if they weren't observed
     - The complete events are included, not just the observed symbols
   - **Future**: Events after the last matching event
   - **Missing**: Symbols that are in the present events but weren't actually observed
   - **Extras**: Symbols that were observed but aren't in the pattern
   - Example 1: Observing `['B'], ['C']` from pattern `[['A'], ['B'], ['C'], ['D']]`:
     - Past: `[['A']]`
     - Present: `[['B'], ['C']]` (both events have matches)
     - Future: `[['D']]`
     - Missing: `[]` (all symbols in present were observed)
   - Example 2: Observing `['a'], ['c']` from pattern `[['a', 'b'], ['c', 'd'], ['e', 'f']]`:
     - Past: `[]` (no events before first match)
     - Present: `[['a', 'b'], ['c', 'd']]` (full events, including unobserved 'b' and 'd')
     - Future: `[['e', 'f']]`
     - Missing: `['b', 'd']` (symbols in present events but not observed)
4. **Empty Event Handling**: Empty events are NOT supported per spec
   - Empty events should be filtered BEFORE observation
   - STM only processes non-empty event sequences
5. **Multi-Modal Processing**: Handles strings, vectors (768-dim), and emotional context
   - Vectors always produce name strings (e.g., 'VECTOR|<hash>') for STM
6. **Deterministic**: Same inputs always produce same outputs
7. **Variable Pattern Lengths**: Supports patterns of arbitrary length (2+ strings total)
   - Events can have varying numbers of symbols
   - Each prediction has unique missing/matches/extras fields based on partial matching
8. **Recall Threshold Behavior**:
   - Range: 0.0 to 1.0
   - Default: 0.1 (permissive matching)
   - **PURPOSE**: Rough filter for pattern matching, NOT exact decimal precision
   - **CRITICAL**: Patterns with NO matches are NEVER returned regardless of threshold
   - **Key Behaviors**:
     - Low values (0.1-0.3): Include more predictions with partial matches
     - Medium values (0.4-0.6): Moderate filtering
     - High values (0.7-0.9): Filter to only high-similarity matches
   - **Implementation Notes**:
     - Uses heuristic calculations for speed - NOT exact to decimal places
     - Threshold comparison uses >= with tolerance (roughly similarity >= recall_threshold)
     - Don't test exact boundary cases where similarity ≈ threshold
     - Similarity calculation may use approximations, not exact ratios
   - **Examples** (approximate behavior):
     - threshold=0.1: Most patterns with any match returned
     - threshold=0.5: Patterns with ~50% or more matches returned
     - threshold=0.9: Only near-perfect matches returned
   - Note: All patterns in KB have frequency ≥ 1 (learned at least once)
9. **Error Handling Philosophy**:
   - **DO NOT mask errors with safe defaults** - errors must be visible for debugging
   - Better to fail explicitly than hide issues with graceful degradation
   - This helps identify and fix root causes rather than papering over problems
   - All calculation errors should raise exceptions with detailed context
10. **Edge Cases and Boundaries**:
   - **Fragmentation**: Can be -1, causing division by zero in potential calculations
   - **Pattern Frequencies**: All patterns have frequency ≥ 1 (no zero-frequency patterns exist)
   - **Empty State**: Hamiltonian calculations require non-empty state
   - **Missing Metadata**: MongoDB metadata documents may be missing, causing None values
   - **Total Ensemble Frequencies**: Can be 0 if no patterns match (even though each pattern has frequency ≥ 1)

## Testing Strategy

The codebase has comprehensive test coverage with 188 test functions across 21 test files. Tests are organized under `tests/tests/`:

1. **Unit Tests** (`tests/tests/unit/`): Test individual components
2. **Integration Tests** (`tests/tests/integration/`): Test end-to-end workflows
3. **API Tests** (`tests/tests/api/`): Test REST endpoints
4. **Performance Tests** (`tests/tests/performance/`): Stress and performance tests

**Test Isolation:**
- Each test gets a unique processor_id for database isolation
- Tests use the fixture from `tests/tests/fixtures/kato_fixtures.py`
- KATO is started once and reused across tests for speed
- Databases are isolated by processor_id to prevent contamination

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
2. Run tests with `./run_simple_tests.sh` to verify changes
3. Debug failures directly with print statements or debugger
4. For production deployment, rebuild with `./kato-manager.sh build`
5. Test full system with `./run_simple_tests.sh` before committing

## Important Files and Locations

- Main processing logic: `kato/workers/kato_processor.py`
- REST API endpoints: `kato/workers/rest_gateway.py`
- Vector operations: `kato/storage/qdrant_manager.py`
- Pattern representations: `kato/representations/pattern.py`
- Pattern processing: `kato/workers/pattern_processor.py`
- Pattern search: `kato/searches/pattern_search.py`
- Metrics calculations: `kato/informatics/metrics.py`
- Test fixtures: `tests/fixtures/kato_fixtures.py`
- Management script: `kato-manager.sh`

## Prediction Metrics and Calculations

### Core Metrics
1. **Hamiltonian**: Entropy-like measure of pattern complexity
   - Requires non-empty state
   - Formula: `sum([expectation(state.count(symbol) / len(state), total_symbols) for symbol in state])`
   - Protected against division by zero when state is empty

2. **Grand Hamiltonian**: Extended hamiltonian using symbol probability cache
   - Calculates entropy using global symbol probabilities
   - Also requires non-empty state

3. **ITFDF Similarity**: Inverse term frequency-document frequency similarity
   - Measures pattern relevance based on frequency and distance
   - Formula: `1 - (distance * prediction['frequency'] / total_ensemble_pattern_frequencies)`
   - Protected against zero total_ensemble_pattern_frequencies

4. **Potential**: Composite metric for ranking predictions
   - Combines: evidence, confidence, SNR, similarity, and fragmentation
   - Formula: `(evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))`
   - Protected against fragmentation = -1 edge case

5. **Confluence**: Probability of pattern occurring vs random chance
   - Formula: `p(e|h) * (1 - conditionalProbability(present, symbol_probabilities))`
   - Returns 0 for empty state

### Required Prediction Fields
All predictions MUST contain these fields:
- `frequency`: Pattern occurrence count
- `matches`: Symbols that match between observation and pattern
- `missing`: Symbols in pattern but not observed
- `evidence`: Strength of pattern match
- `confidence`: Ratio of matches to present length
- `snr`: Signal-to-noise ratio
- `fragmentation`: Pattern cohesion measure (can be -1)
- `emotives`: Emotional context data
- `present`: Events containing matching symbols

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

### ⚠️ MANDATORY test-analyst REQUIREMENTS:
The test-analyst agent MUST:
1. **ALWAYS check for code changes and rebuild containers when needed**:
   - Check `git diff` to detect ANY code changes (*.py, *.sh, Dockerfile*, requirements*.txt, etc.)
   - Check file modification times against container build times
   - Run `./check-rebuild-needed.sh` to verify containers are current
   - If ANY source files changed: rebuild BOTH containers:
     - `./kato-manager.sh build` for KATO image
     - `./test-harness.sh build` for test harness
   - NEVER skip rebuild when ANY code files are modified
   - Verify rebuild completed successfully before proceeding

2. **ALWAYS run actual tests** - NEVER use cached or simulated results:
   - Must execute `./test-harness.sh test` or similar commands
   - Must wait for actual test completion
   - Test output is saved to `logs/test-runs/` to prevent memory issues
   - NEVER return results without actual execution

3. **Read test results from log files** (NEW APPROACH):
   - **Primary**: Read `logs/test-runs/latest/summary.txt` for quick overview
   - **Errors**: Check `logs/test-runs/latest/errors.log` for failure details
   - **Full output**: Only read `logs/test-runs/latest/output.log` if debugging
   - Use `tail -n 1000` to read portions of large files
   - Report file paths where full logs are saved

4. **AUTOMATICALLY FIX TEST INFRASTRUCTURE ISSUES**:
   The test-analyst has FULL AUTHORITY to fix operational problems that prevent tests from running:
   
   **Issues to Auto-Fix:**
   - Python syntax errors in test files (indentation, imports, etc.)
   - Missing or broken test fixtures
   - Test harness script errors (test-harness.sh, kato-manager.sh)
   - Docker container build failures
   - Missing dependencies in requirements-test.txt
   - Pytest configuration issues (pytest.ini, conftest.py)
   - Path or import errors in test files
   - File permission issues on test scripts
   
   **Auto-Fix Protocol:**
   1. If test execution fails before tests can run:
      - Diagnose the root cause (syntax error, missing file, etc.)
      - Fix the issue directly (edit files, add dependencies, fix permissions)
      - Document what was fixed and why
      - Retry test execution
      - Continue until tests can actually run
   
   **DO NOT Auto-Fix:**
   - Actual test logic or assertions (these are intentional)
   - KATO source code (only test infrastructure)
   - Test expectations that reflect actual KATO behavior
   
   **Example Auto-Fix Scenarios:**
   - `IndentationError` → Fix indentation in test file
   - `ModuleNotFoundError` → Add missing import or install dependency
   - `Permission denied` → chmod +x on script files
   - `Docker build failed` → Fix Dockerfile.test or dependencies
   - `pytest collection error` → Fix syntax or import issues

### Example Usage:
```
assistant: "I've completed the bug fix. Let me use the test-analyst to verify all tests pass."
<uses Task tool with subagent_type="test-analyst">

The test-analyst MUST:
1. Check for ANY code changes: git diff
2. Run rebuild check: ./check-rebuild-needed.sh
3. Rebuild containers if needed:
   - ./kato-manager.sh build (if KATO source changed)
   - ./test-harness.sh build (if test files changed)
4. Attempt to run tests: ./test-harness.sh test
4. IF tests fail to start/collect:
   - Diagnose the infrastructure issue
   - Fix it automatically (edit files, fix permissions, etc.)
   - Document the fix
   - Retry test execution
5. Once tests complete:
   - Read results from `logs/test-runs/latest/summary.txt`
   - Check errors in `logs/test-runs/latest/errors.log`
   - Only read full output if specifically debugging issues
   - Report summary with file paths to full logs
   - Analyze patterns and provide recommendations
```

## Test Isolation Architecture

### Critical Requirement: Complete Database Isolation
Each KATO instance MUST have complete isolation via unique processor_id to prevent cross-contamination between tests and production instances.

### Database Isolation Strategy
Each KATO instance uses its processor_id for complete database isolation:

1. **MongoDB**: Database name = processor_id
   - Patterns stored in `{processor_id}.patterns_kb`
   - Symbols stored in `{processor_id}.symbols_kb`
   - Predictions stored in `{processor_id}.predictions_kb`
   - Metadata stored in `{processor_id}.metadata`

2. **Qdrant**: Collection name = `vectors_{processor_id}`
   - Vector embeddings isolated per instance
   - No cross-contamination between tests
   - Each instance has its own HNSW index

3. **In-Memory Cache**: Per VectorSearchEngine instance
   - Cache is automatically isolated per engine instance
   - No shared state between processors

### Test Requirements
- **Each test MUST use a unique processor_id**
- Format: `test_{test_name}_{timestamp}_{uuid}`
- Example: `test_pattern_endpoint_1699123456789_a1b2c3d4`
- **Fixture scope is 'function'** - each test gets fresh instance
- **Cleanup is automatic** in fixture teardown

### Production Requirements
- **Each production instance MUST have unique processor_id**
- Never share processor_ids between instances
- Monitor for ID collisions
- Use format: `{environment}_{service}_{timestamp}_{uuid}`

### Why This Matters
Without proper isolation:
- Tests contaminate each other's long-term memory
- Patterns learned in one test affect predictions in another
- Test failures become non-deterministic
- Parallel test execution becomes impossible

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