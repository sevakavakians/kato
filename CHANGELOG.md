# Changelog

All notable changes to KATO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
