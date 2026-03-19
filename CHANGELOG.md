# Changelog

All notable changes to KATO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- **MongoDB Dead Code**: Removed `connection_pool.py`, `MongoDBConfig`, `DatabaseManager`, and pymongo imports
- **MongoDB Fallback Logic**: Hybrid architecture (ClickHouse + Redis) is now the only mode; no MongoDB fallback

### Changed
- Default `KATO_ARCHITECTURE_MODE` changed from `mongodb` to `hybrid`
- `update_pattern()` and `delete_pattern()` now use ClickHouse/Redis instead of MongoDB APIs

### Documentation
- Fixed README.md: updated container tags (v2.0.0 → v3.4.0), test counts (185 → 445+), broken doc links
- Fixed ARCHITECTURE_DIAGRAM.md: single instance on port 8000, correct ClickHouse columns, added FilterPipelineExecutor
- Updated MODE_SWITCHING.md: removed MongoDB mode, hybrid is the only architecture
- Updated known-issues.md: refreshed test counts and removed stale September 2025 issues

## [3.4.0] - 2026-03-15

### Added
- **Database Authentication**: Optional authentication support for ClickHouse, Redis, and Qdrant

### Fixed
- Prevent empty Qdrant API key from blocking all vector operations

## [3.3.1] - 2026-03-10

### Fixed
- Minor stability improvements

## [3.3.0] - 2026-02-20

### Added
- **Redis OOM Protection**: Comprehensive memory monitoring and Redis protection
- **Manager Enhancements**: Memory monitoring command for kato-manager.sh
- **Request Limit**: Increased uvicorn request limit from 10k to 100k for training workloads

### Fixed
- Use `_run_async_in_sync` for vector sync wrappers to prevent event loop crash
- Recreate ClickHouse schema after clean-data command

## [3.2.1] - 2026-01-28

### Fixed
- Prevent ClickHouse system log bloat causing memory exhaustion

### Added
- Semantic version display in kato-manager.sh status command

## [3.2.0] - 2026-01-15

### Added
- **Single-Symbol Predictions**: 1+ STM prediction support with fast path optimization (previously required 2+ symbols)

### Fixed
- Remove DEBUG prefixes from production INFO-level logs

## [3.1.2] - 2025-12-20

### Fixed
- Remove DEBUG prefixes from production INFO-level logs

## [3.1.1] - 2025-12-16

### Fixed
- Resolve critical deployment configuration bugs for fresh installations
- Auto-create Docker network in deployment package

## [3.1.0] - 2025-12-12

### Added
- **Fuzzy Token Matching**: Token-level similarity matching with configurable threshold (0.0-1.0)
  - Uses RapidFuzz for 5-10x faster similarity calculation vs difflib
  - Configurable via `fuzzy_token_threshold` parameter (default: 0.0, disabled)
  - New `anomalies` field in predictions tracking fuzzy matches with similarity scores
  - Handles typos, misspellings, and minor token variations
  - Recommended threshold: 0.85 for balanced fuzzy matching
  - Complete documentation across 9 documentation files

### Changed
- Removed exception masking in metric calculations for better error visibility

### Documentation
- Updated reference docs: configuration-vars.md, session-configuration.md, prediction-object.md
- Updated API docs: api/configuration.md, api/predictions.md
- Updated research docs: pattern-matching.md
- Updated user docs: configuration.md, predictions.md

## [3.0.2] - 2025-11-13

### Added
- Container image versioning with semantic version tags
- OCI-compliant image labels for metadata
- `build-and-push.sh` script for automated multi-tag builds
- `bump-version.sh` utility for version management
- CHANGELOG.md for version history tracking
- RELEASING.md for release process documentation

### Changed
- Standardized version to 3.0.2 across all files (pyproject.toml, setup.py, __init__.py)
- Enhanced Dockerfile with version build arguments

## [2.0.0] - 2025-10-31

### Added
- **GPU Optimization Foundation**: CUDA-accelerated pattern matching with cuPy integration
- **Token-level Pattern Matching**: Configurable matching mode with exact difflib compatibility
- **Standalone Deployment Package**: Pre-built container images for simplified deployment
- **Session Auto-Extension**: Sliding window session expiration for long-running tasks
- **WebSocket Event Notifications**: Real-time session monitoring and updates
- **Session Isolation**: Complete STM isolation per user session with Redis-backed state
- **Write Guarantees**: MongoDB majority write concern to prevent data loss

### Changed
- **FastAPI Architecture**: Direct embedding of KATO processor (removed REST/ZMQ complexity)
- **Vector Database**: Migrated from linear search to Qdrant (10-100x performance improvement)
- **HTTP Client**: Migrated from aiohttp to httpx for 100% reliable concurrent requests
- **Configuration Optimization**: Tuned for hierarchical training workloads

### Fixed
- Broken performance benchmark in RapidFuzz unit tests
- KATO_SERVICES_RUNNING gate interference in RapidFuzz tests
- Prediction computation when `process_predictions=False`
- Missing asyncio import in sessions endpoint
- Session expiration during long-running training operations
- Race condition in session lock creation causing lost observations
- Event alignment for missing/extras fields in predictions
- Resource cleanup on processor eviction
- Missing trace_context context manager causing ImportError

### Performance
- 3.57x throughput improvement
- 72% latency reduction
- Comprehensive CPU optimizations
- Connection retry logic for improved reliability
- Optimized session storage (TTL-only updates to prevent race conditions)

### Documentation
- Documented observe_sequence emotives and metadata placement behavior
- Comprehensive logging technical debt cleanup
- Enhanced API endpoint documentation

## [1.0.0] - 2024-09-15

### Added
- Initial public release
- Core KATO processor with deterministic learning
- MongoDB pattern storage with SHA1-based pattern identification
- Basic vector storage with linear search
- FastAPI service with core endpoints
- Multi-modal support (strings, vectors, emotives)
- Temporal prediction with past/present/future segmentation
- Auto-learning modes (CLEAR and ROLLING)
- Docker Compose deployment with MongoDB, Redis, and Qdrant

### Features
- Deterministic pattern learning and recall
- Emotive context tracking with rolling windows
- Pattern metadata with set-union accumulation
- Short-term and long-term memory architecture
- Configurable recall thresholds
- Pattern frequency tracking
- Session-based configuration

---

## Version History

- **3.4.0** (2026-03-15): Database authentication support
- **3.3.0** (2026-02-20): Redis OOM protection, memory monitoring
- **3.2.0** (2026-01-15): Single-symbol predictions, ClickHouse memory fix
- **3.1.0** (2025-12-12): Fuzzy token matching with RapidFuzz
- **3.0.2** (2025-11-13): Container image versioning
- **2.0.0** (2025-10-31): Major architecture modernization, GPU support, performance optimizations
- **1.0.0** (2024-09-15): Initial public release

---

## Upgrade Notes

### Upgrading to 2.0.0

**Breaking Changes:**
- API endpoint migration to session-based architecture
- FastAPI direct embedding (removed REST/ZMQ services)
- Vector database change from custom implementation to Qdrant

**Migration Steps:**
1. Update docker compose.yml to use new service configuration
2. Migrate existing patterns to Qdrant (migration script provided)
3. Update client code to use session-based endpoints
4. Review and update configuration for new defaults

**Compatibility:**
- Automatic session middleware provides backward compatibility for non-session endpoints
- Existing pattern data can be migrated without loss

---

## Contributing

When adding entries to the CHANGELOG:
1. Add unreleased changes under `[Unreleased]` section
2. Categorize changes: Added, Changed, Deprecated, Removed, Fixed, Security, Performance, Documentation
3. Use present tense ("Add feature" not "Added feature")
4. Reference issue numbers when applicable
5. On release, move `[Unreleased]` entries to new version section with date
