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
# Start all services (ClickHouse, Qdrant, Redis, KATO)
./start.sh

# Stop services
docker-compose down

# Restart services
docker-compose restart

# Check status
docker-compose ps

# View logs
docker-compose logs                      # All services
docker-compose logs kato                 # KATO service
docker logs kato --tail 50               # Direct Docker logs
```

### Service URLs
After running `./start.sh`:
- **KATO Service**: http://localhost:8000
- **ClickHouse**: http://localhost:8123
- **Qdrant**: http://localhost:6333
- **Redis**: redis://localhost:6379
- **API Docs**: http://localhost:8000/docs

### Testing
```bash
# IMPORTANT: Services must be running first!
./start.sh

# Set up virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Run all tests (with running services)
./run_tests.sh --no-start --no-stop

# Run specific test categories
./run_tests.sh --no-start --no-stop tests/tests/unit/
./run_tests.sh --no-start --no-stop tests/tests/integration/
./run_tests.sh --no-start --no-stop tests/tests/api/

# Run specific test file
./run_tests.sh --no-start --no-stop tests/tests/unit/test_observations.py

# Run with options
./run_tests.sh --no-start --no-stop -v    # Verbose output

# Run tests directly with pytest
source venv/bin/activate
python -m pytest tests/tests/unit/ -v --tb=short
```

**Key Features:**
- Tests run in local Python, connect to running KATO service
- Each test gets unique processor_id for complete isolation
- Direct debugging with print statements and breakpoints
- Fast iteration - no container builds for tests
- Tests can run in parallel safely

### Health Checks and Debugging
```bash
# Check service health
curl http://localhost:8000/health

# Test basic operations
curl -X POST http://localhost:8000/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

# Test bulk observation endpoint
curl -X POST http://localhost:8000/observe-sequence \
  -H "Content-Type: application/json" \
  -d '{"observations": [{"strings": ["test1"]}, {"strings": ["test2"]}]}'

# View API documentation
open http://localhost:8000/docs     # macOS
xdg-open http://localhost:8000/docs # Linux

# Check database connections
curl http://localhost:8123/ping   # ClickHouse
curl http://localhost:6333/health   # Qdrant
docker exec kato-redis redis-cli ping   # Redis
```

## High-Level Architecture

### FastAPI Architecture (Current)
```
Client Request → FastAPI Service (Port 8000) → Embedded KATO Processor
                           ↓                                    ↓
                    Async Processing              ClickHouse, Qdrant & Redis
                           ↓                     (Isolated by session_id)
                    JSON Response
```

### Core Components

1. **FastAPI Service** (`kato/services/kato_fastapi.py`)
   - Direct embedding of KATO processor
   - Async request handling with FastAPI
   - Core endpoints: `/observe`, `/observe-sequence`, `/learn`, `/predictions`, `/health`, `/status`
   - Bulk processing: `/observe-sequence` for batch observations with isolation options
   - Advanced endpoints: `/pattern/{id}`, `/percept-data`, `/cognition-data`, `/metrics`
   - Session configuration: `/sessions/{session_id}/config`
   - STM endpoints: `/stm` (alias: `/short-term-memory`)
   - Clear endpoints: `/clear-stm`, `/clear-all` (with aliases)
   - WebSocket support at `/ws` for real-time communication

2. **KATO Processor** (`kato/workers/kato_processor.py`)
   - Core AI engine managing observations and predictions
   - Maintains short-term memory and long-term memory
   - Coordinates with vector database for similarity searches
   - Implements deterministic hashing for pattern identification

3. **Storage Layer** (`kato/storage/`)
   - **Pattern Storage**: ClickHouse with multi-stage filter pipeline (MinHash/LSH/Bloom)
   - **Metadata Cache**: Redis for pattern frequency and emotive profiles
   - **Vector Storage**: Qdrant with HNSW indexing for 10-100x performance
   - **Session Storage**: Redis for fast session state management
   - Hybrid architecture for billion-scale performance

### Memory Architecture

- **Short-Term Memory (STM)**: Temporary storage for current observation sequences
- **Long-Term Memory**: Persistent storage with `PTRN|<sha1_hash>` identifiers
- **Pattern Storage**: ClickHouse partitioned by kb_id for node isolation
- **Vector Storage**: Modern Qdrant database with collection per kb_id
- **Pattern Hashing**: SHA1-based deterministic pattern identification

### ClickHouse Pattern Storage

- **Partitioning**: Patterns partitioned by kb_id for node isolation
- **Unique Indexing**: Primary key on (kb_id, name) with Bloom filter
- **Multi-Stage Filter Pipeline**: MinHash → LSH → Bloom → ClickHouse for billion-scale
- **Frequency Tracking**: Each re-learning of same pattern increments frequency counter
  - Minimum frequency = 1 (pattern must be learned at least once to exist)
  - Frequency increments each time the same pattern is re-learned
  - Frequencies cached in Redis for fast access
- **Pattern Naming**: Pattern names stored WITHOUT 'PTRN|' prefix (plain SHA1 hash)
- **Storage Guarantee**: Only one record per unique pattern per kb_id

### Key Behavioral Properties

1. **Minimum Sequence Length**: KATO requires at least 2 strings total in STM to generate predictions
   - Valid: `[['A', 'B']]` (2 strings in 1 event)
   - Valid: `[['A'], ['B']]` (2 strings across 2 events)
   - Valid: `[['A']] + vectors` (1 user string + vector strings like 'VCTR|<hash>')
   - Invalid: `[['A']]` (only 1 string without vectors - no predictions generated)

2. **Auto-Learning Modes**: Two STM modes control behavior after reaching MAX_PATTERN_LENGTH
   - **CLEAR Mode** (default): Traditional behavior - STM is completely emptied after auto-learn
   - **ROLLING Mode**: STM maintained as sliding window (size = MAX_PATTERN_LENGTH - 1)
     - Enables continuous learning of overlapping patterns
     - Every new observation triggers learning and oldest event removal
     - Example: With MAX_PATTERN_LENGTH=3, sequence A→B→C→D→E learns patterns ABC, BCD, CDE
3. **Alphanumeric Sorting**: Strings within events are sorted alphanumerically for consistency
4. **Temporal Segmentation**: Predictions structured as past/present/future
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
5. **Empty Event Handling**: Empty events are NOT supported per spec
   - Empty events should be filtered BEFORE observation
   - STM only processes non-empty event sequences
6. **Multi-Modal Processing**: Handles strings, vectors (768-dim), and emotional context
   - Vectors always produce name strings (e.g., 'VCTR|<hash>') for STM
7. **Deterministic**: Same inputs always produce same outputs
8. **Variable Pattern Lengths**: Supports patterns of arbitrary length (2+ strings total)
   - Events can have varying numbers of symbols
   - Each prediction has unique missing/matches/extras fields based on partial matching
9. **Recall Threshold Behavior**:
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
10. **Error Handling Philosophy**:
   - **DO NOT mask errors with safe defaults** - errors must be visible for debugging
   - Better to fail explicitly than hide issues with graceful degradation
   - This helps identify and fix root causes rather than papering over problems
   - All calculation errors should raise exceptions with detailed context
11. **Edge Cases and Boundaries**:
   - **Fragmentation**: Can be -1, causing division by zero in potential calculations
   - **Pattern Frequencies**: All patterns have frequency ≥ 1 (no zero-frequency patterns exist)
   - **Empty State**: Normalized entropy calculations require non-empty state
   - **Missing Metadata**: Redis metadata keys may be missing, causing None values
   - **Total Ensemble Frequencies**: Can be 0 if no patterns match (even though each pattern has frequency ≥ 1)

## Testing Strategy

The codebase has comprehensive test coverage with 287 test functions across multiple test files. Tests are organized under `tests/tests/`:

1. **Unit Tests** (`tests/tests/unit/`): Test individual components
2. **Integration Tests** (`tests/tests/integration/`): Test end-to-end workflows
3. **API Tests** (`tests/tests/api/`): Test REST endpoints
4. **Performance Tests** (`tests/tests/performance/`): Stress and performance tests

**Test Isolation:**
- Each test gets a unique processor_id for database isolation
- Tests use the fixture from `tests/tests/fixtures/kato_fixtures.py`
- KATO services must be running before tests
- Databases are isolated by processor_id to prevent contamination
- Tests run in local Python environment for fast debugging

## Configuration

### Environment Variables

#### Core Configuration
- `PROCESSOR_ID`: Unique identifier for processor instance
- `PROCESSOR_NAME`: Display name for the processor
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)

#### Database Configuration
- `CLICKHOUSE_HOST`: ClickHouse host (default: localhost)
- `CLICKHOUSE_PORT`: ClickHouse HTTP port (default: 8123)
- `CLICKHOUSE_DB`: ClickHouse database name (default: kato)
- `QDRANT_HOST`: Qdrant host (default: localhost)
- `QDRANT_PORT`: Qdrant port (default: 6333)
- `REDIS_URL`: Redis connection URL

#### Learning Configuration
- `MAX_PATTERN_LENGTH`: Auto-learn after N observations (0 = manual only, default: 0)
  - When auto-learn triggers, behavior depends on STM_MODE
- `STM_MODE`: Short-term memory mode after auto-learn (default: 'CLEAR')
  - 'CLEAR': STM is completely cleared after auto-learn (original behavior)
  - 'ROLLING': STM is maintained as sliding window for continuous learning
- `PERSISTENCE`: Rolling window size for emotive values per pattern (default: 5)
  - Controls how many historical emotive entries are kept when patterns are re-learned
- `RECALL_THRESHOLD`: Pattern matching threshold (0.0-1.0, default: 0.1)

#### Processing Configuration
- `INDEXER_TYPE`: Vector indexer type (default: 'VI')
- `MAX_PREDICTIONS`: Maximum predictions to return (default: 100)
- `SORT`: Sort symbols alphabetically within events (default: true)
- `PROCESS_PREDICTIONS`: Enable prediction processing (default: true)

### Session-Based Configuration
The system uses Redis-based session management for configuration:
- **Session Isolation**: Each session gets unique configuration
- **Dynamic Configuration**: Settings can be changed per session
- **Persistent State**: Session data persists across service restarts
- **Configuration via API**: Use session endpoints to modify behavior

## Recent Modernizations

- **FastAPI Migration**: Replaced REST/ZMQ with direct FastAPI embedding (2025-09)
- **Vector Database**: Migrated from linear search to Qdrant (10-100x faster)
- **Simplified Architecture**: Removed connection pooling complexity
- **Better Testing**: Local Python tests with automatic isolation

## Development Workflow

1. Make changes to source files in `kato/` directory
2. Restart services: `docker-compose restart`
3. Run tests: `./run_tests.sh --no-start --no-stop`
4. Debug failures directly with print statements or debugger
5. Commit changes when tests pass

## Important Files and Locations

- Main service: `kato/services/kato_fastapi.py`
- Processing logic: `kato/workers/kato_processor.py`
- Vector operations: `kato/storage/qdrant_manager.py`
- Pattern representations: `kato/representations/pattern.py`
- Pattern processing: `kato/workers/pattern_processor.py`
- Pattern search: `kato/searches/pattern_search.py`
- Metrics calculations: `kato/informatics/metrics.py`
- Test fixtures: `tests/tests/fixtures/kato_fixtures.py`
- Startup script: `start.sh`

## Prediction Metrics and Calculations

### Core Metrics
1. **Normalized Entropy**: Entropy-like measure of pattern complexity
   - Requires non-empty state
   - Formula: `sum([expectation(state.count(symbol) / len(state), total_symbols) for symbol in state])`
   - Protected against division by zero when state is empty

2. **Global Normalized Entropy**: Extended normalized entropy using symbol probability cache
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

## Emotives and PERSISTENCE

### Quick Reference
- **Input Format**: `Dict[str, float]` - e.g., `{"happiness": 0.8, "arousal": -0.3}`
- **Storage**: Rolling window arrays per pattern, limited by PERSISTENCE parameter
- **PERSISTENCE**: Controls window size (default: 5) - how many historical values kept
- **Averaging**: Multiple emotive values are averaged (arithmetic mean)
- **Critical**: Emotives in predictions come from learned patterns, NOT current observations

### Data Flow
1. Observation includes emotives dict
2. Added to STM accumulator list
3. Averaged when learning pattern
4. Stored in Redis with rolling window (LPUSH/LTRIM)
5. Retrieved and averaged in predictions

### Rolling Window Behavior
With PERSISTENCE=5, pattern's emotive arrays maintain last 5 values:
```python
# Array grows until limit
[0.8] → [0.8, 0.6] → [0.8, 0.6, 0.9] → [0.8, 0.6, 0.9, 0.7] → [0.8, 0.6, 0.9, 0.7, 0.5]
# Next value pushes off oldest
[0.6, 0.9, 0.7, 0.5, 0.3]  # 0.8 dropped
```

### Configuration Guidelines
- `PERSISTENCE=1`: Instant adaptation (only latest value)
- `PERSISTENCE=5`: Default, balanced adaptation
- `PERSISTENCE=10+`: Slower adaptation, longer memory

### Testing Emotives
```python
# 1. Learn pattern WITH emotives
kato.observe({'strings': ['A'], 'emotives': {'joy': 0.8}})
kato.observe({'strings': ['B'], 'emotives': {'joy': 0.6}})
kato.learn()

# 2. Clear STM and observe matching pattern
kato.clear_short_term_memory()
kato.observe({'strings': ['A', 'B']})

# 3. Predictions will contain averaged emotives from learned pattern
predictions = kato.get_predictions()
# predictions[0]['emotives'] will have averaged values
```

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

### ⚠️ CRITICAL: Use test-analyst Agent ONLY for Docker-based Testing ⚠️

With the new FastAPI architecture, most testing is done locally with Python:

### Local Testing (Recommended)
```bash
# Ensure services are running
./start.sh

# Run tests locally
./run_tests.sh --no-start --no-stop

# Direct pytest execution
python -m pytest tests/tests/unit/ -v
```

### When to Use test-analyst Agent:
The test-analyst agent should ONLY be used for:
- Running tests that require Docker container rebuilds
- Complex test orchestration across multiple containers
- Performance benchmarking with isolated environments

For regular development testing, use the local Python approach described above.

## Test Isolation Architecture

### Critical Requirement: Complete Database Isolation
Each KATO instance MUST have complete isolation via unique kb_id to prevent cross-contamination between tests and production instances.

### Database Isolation Strategy
Each KATO instance uses its kb_id for complete database isolation:

1. **ClickHouse**: Partitioning by kb_id
   - Patterns stored in `patterns` table partitioned by kb_id
   - Primary key on (kb_id, name) ensures uniqueness
   - Query filters automatically include kb_id for isolation

2. **Redis**: Key namespacing by kb_id
   - Pattern frequencies: `freq:{kb_id}:{pattern_name}`
   - Emotive profiles: `emotives:{kb_id}:{pattern_name}`
   - Session state: `session:{session_id}`

3. **Qdrant**: Collection name = `vectors_{kb_id}`
   - Vector embeddings isolated per instance
   - No cross-contamination between tests
   - Each instance has its own HNSW index

4. **In-Memory Cache**: Per processor instance
   - Cache is automatically isolated per processor
   - No shared state between processors

### Test Requirements
- **Each test MUST use a unique kb_id**
- Format: `test_{test_name}_{timestamp}_{uuid}`
- Example: `test_pattern_endpoint_1699123456789_a1b2c3d4`
- **Fixture scope is 'function'** - each test gets fresh isolation
- **Services must be running** before tests execute

### Production Requirements
- **Each production instance MUST have unique kb_id**
- Never share kb_ids between instances
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
2. **test-analyst**: Docker-based testing and complex test orchestration ONLY
3. **general-purpose**: Complex multi-step research tasks
4. **statusline-setup**: Configure Claude Code status line

### Quick Decision Tree:
- Updating documentation? → project-manager
- Running Docker tests? → test-analyst
- Running local tests? → Do it directly with `./run_tests.sh`
- Complex research? → general-purpose
- Everything else? → Do it directly

### Common Mistakes to Avoid:
1. ❌ Editing planning-docs/ directly → ✅ Use project-manager
2. ❌ Using test-analyst for local tests → ✅ Use `./run_tests.sh`
3. ❌ Forgetting to start services before tests → ✅ Run `./start.sh` first
4. ❌ Sharing kb_ids between tests → ✅ Each test gets unique kb_id
- **ALWAYS** rebuild KATO docker image using no-cache options after **EVERY** code update and **BEFORE** testing.
- Do **NOT** use MCPs for this project.