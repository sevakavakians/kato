# KATO Changelog Guidelines

## Overview

KATO follows [Keep a Changelog](https://keepachangelog.com/) format. This document provides guidelines for writing clear, useful changelog entries.

See [CHANGELOG.md](/CHANGELOG.md) for the project's changelog.

## Table of Contents
1. [Changelog Format](#changelog-format)
2. [Entry Categories](#entry-categories)
3. [Writing Guidelines](#writing-guidelines)
4. [Conventional Commits](#conventional-commits)
5. [Examples](#examples)

## Changelog Format

### Structure

```markdown
# Changelog

All notable changes to KATO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature X

### Changed
- Updated feature Y

### Deprecated
- Feature Z is deprecated

### Removed
- Removed feature A

### Fixed
- Fixed bug B

### Security
- Security patch C

## [3.1.0] - 2025-11-13

### Added
- New /metrics endpoint for session statistics
- Support for custom metadata in observations

### Changed
- Improved pattern matching performance by 15%

## [3.0.0] - 2025-10-31

### Added
- Session-based architecture
- Redis-backed session state

### Removed
- Deprecated REST/ZMQ architecture
```

### Version Header Format

```markdown
## [VERSION] - YYYY-MM-DD
```

Examples:
```markdown
## [3.1.0] - 2025-11-13
## [3.0.1] - 2025-11-10
## [Unreleased]
```

## Entry Categories

### Added

For **new features and capabilities**.

```markdown
### Added
- New /sessions/{id}/metrics endpoint for retrieving session statistics
- Support for custom metadata fields in observations
- WebSocket support for real-time prediction notifications
- GPU acceleration for pattern matching (experimental)
```

### Changed

For **changes in existing functionality**.

```markdown
### Changed
- Improved pattern matching algorithm performance by 15%
- Updated Redis connection pooling strategy
- Changed default session TTL from 1800s to 3600s
- Migrated from aiohttp to httpx for HTTP client
```

### Deprecated

For **soon-to-be removed features**.

```markdown
### Deprecated
- /observe endpoint deprecated in favor of /sessions/{id}/observe
- `USE_LEGACY_MODE` configuration option (will be removed in v4.0)
- Character-level matching mode (use token-level instead)
```

### Removed

For **removed features** (breaking changes).

```markdown
### Removed
- REST/ZMQ architecture (replaced with FastAPI direct embedding)
- Support for Python 3.7 and 3.8
- Legacy /observe endpoint (use /sessions/{id}/observe)
```

### Fixed

For **bug fixes**.

```markdown
### Fixed
- Pattern matching no longer returns duplicate results
- Session TTL now extends properly on activity
- Memory leak in session cleanup process
- Race condition in concurrent observation processing
```

### Security

For **security-related changes**.

```markdown
### Security
- Updated dependencies to patch CVE-2025-12345
- Fixed SQL injection vulnerability in pattern queries
- Improved session ID generation for better randomness
```

### Performance

For **performance improvements** (optional category).

```markdown
### Performance
- 3.57x throughput improvement in prediction generation
- 72% latency reduction in pattern matching
- Optimized ClickHouse query patterns
```

## Writing Guidelines

### Be Specific

❌ **Bad:**
```markdown
- Fixed bugs
- Updated dependencies
- Improved performance
```

✅ **Good:**
```markdown
- Fixed pattern matching returning duplicates for similar patterns
- Updated httpx to 0.25.0 to fix connection pooling issue
- Improved prediction generation performance by 3.5x through caching
```

### Include Context

❌ **Bad:**
```markdown
- Added metrics endpoint
```

✅ **Good:**
```markdown
- Added /sessions/{id}/metrics endpoint for retrieving session statistics including observation count, pattern count, and memory usage
```

### Use Action Verbs

✅ **Good verbs:**
- Added, Implemented, Introduced
- Changed, Updated, Modified, Improved
- Deprecated
- Removed, Deleted
- Fixed, Resolved, Corrected
- Enhanced, Optimized

### Target Audience

Write for **users of KATO**, not developers:

❌ **Bad (too technical):**
```markdown
- Refactored SessionManager class to use async/await pattern
```

✅ **Good (user-focused):**
```markdown
- Improved session management reliability and performance
```

### Breaking Changes

Clearly mark breaking changes:

```markdown
### Removed
- **BREAKING**: Removed /observe endpoint. Use /sessions/{id}/observe instead.
  Migration: Replace `/observe` calls with `/sessions/{session_id}/observe`

### Changed
- **BREAKING**: Changed emotives field from optional to required in observe requests
  Migration: Provide empty dict `{}` if no emotives needed
```

### Reference Issues

Link to GitHub issues when relevant:

```markdown
### Fixed
- Fixed pattern matching duplicates (#123)
- Resolved session TTL extension issue (#145)
```

## Conventional Commits

### Commit Message Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types

- `feat:` - New feature (CHANGELOG: Added)
- `fix:` - Bug fix (CHANGELOG: Fixed)
- `docs:` - Documentation only (CHANGELOG: Documentation)
- `style:` - Formatting, no code change (no CHANGELOG)
- `refactor:` - Code refactoring (CHANGELOG: Changed)
- `perf:` - Performance improvement (CHANGELOG: Performance)
- `test:` - Adding tests (no CHANGELOG)
- `chore:` - Maintenance tasks (no CHANGELOG unless user-facing)

### Examples

```bash
# Feature (goes in "Added" section)
git commit -m "feat: add metrics endpoint for session statistics"

# Bug fix (goes in "Fixed" section)
git commit -m "fix: pattern matching returning duplicates"

# Breaking change (mark clearly)
git commit -m "feat!: remove deprecated /observe endpoint

BREAKING CHANGE: The /observe endpoint has been removed.
Use /sessions/{session_id}/observe instead."

# Performance improvement
git commit -m "perf: optimize pattern matching with caching (3.5x faster)"

# Documentation
git commit -m "docs: update API reference with new endpoints"
```

### Mapping Commits to Changelog

When preparing release:

```bash
# View commits since last release
git log v3.0.0..HEAD --oneline

# Group by type
git log v3.0.0..HEAD --oneline | grep "^feat:"    # → Added
git log v3.0.0..HEAD --oneline | grep "^fix:"     # → Fixed
git log v3.0.0..HEAD --oneline | grep "^perf:"    # → Performance
```

## Examples

### Example Release: v3.1.0

```markdown
## [3.1.0] - 2025-11-13

### Added
- New /sessions/{id}/metrics endpoint for retrieving session statistics
- Support for custom metadata fields in observation requests
- WebSocket notifications for real-time prediction updates
- Prometheus metrics export endpoint at /prometheus-metrics
- Configuration option for custom pattern matching algorithms

### Changed
- Improved pattern matching performance by 15% through caching
- Updated default recall_threshold from 0.1 to 0.2 for better precision
- Enhanced session cleanup to prevent memory leaks
- Migrated from aiohttp to httpx for improved reliability

### Fixed
- Pattern matching no longer returns duplicate results
- Session TTL now properly extends on activity
- Race condition in concurrent observation processing
- Vector embeddings now properly normalized before storage

### Performance
- 3.5x faster prediction generation through optimized queries
- Reduced Redis memory usage by 40% with improved serialization
- ClickHouse query optimization reduces latency by 50ms

### Documentation
- Added comprehensive integration examples
- Updated API reference with all new endpoints
- Added troubleshooting guide for common issues
```

### Example Hotfix: v3.0.1

```markdown
## [3.0.1] - 2025-11-10

### Fixed
- Critical: Fixed memory leak in session cleanup causing OOM errors
- Session auto-extension now works correctly with sliding window
- Pattern de-duplication in predictions

### Security
- Updated dependencies to patch security vulnerabilities
```

### Example Major Release: v4.0.0

```markdown
## [4.0.0] - 2026-01-15

### Added
- Distributed pattern storage across multiple nodes
- Built-in authentication and authorization
- GraphQL API alongside REST

### Changed
- **BREAKING**: Session API now requires authentication headers
- **BREAKING**: Changed default port from 8000 to 8080
- **BREAKING**: Emotives field now required in observe requests

### Removed
- **BREAKING**: Removed deprecated /observe endpoint
- **BREAKING**: Removed support for Python 3.8 and 3.9
- **BREAKING**: Removed legacy REST/ZMQ architecture

### Migration Guide
See [MIGRATION_v4.md](MIGRATION_v4.md) for detailed upgrade instructions.
```

## Best Practices

1. **Update frequently** - Add entries as you work
2. **Be user-focused** - Write for KATO users, not developers
3. **Group logically** - Related changes in same category
4. **Breaking changes first** - Most important information first
5. **Include examples** - Show before/after for breaking changes
6. **Link issues** - Reference GitHub issues
7. **Date releases** - Always include release date
8. **Keep Unreleased** - Always have [Unreleased] section
9. **Review before release** - Ensure clarity and completeness
10. **Follow conventions** - Consistent formatting

## Checklist for Release

Before releasing, ensure CHANGELOG has:

- [ ] All significant changes documented
- [ ] Changes categorized correctly (Added, Changed, Fixed, etc.)
- [ ] Breaking changes clearly marked
- [ ] User-focused descriptions (not too technical)
- [ ] Version and date in header
- [ ] [Unreleased] section moved to version section
- [ ] New empty [Unreleased] section at top
- [ ] Grammar and spelling checked
- [ ] Links to issues included
- [ ] Migration guides referenced (if breaking changes)

## Related Documentation

- [Release Process](releasing.md)
- [Version Management](version-management.md)
- [Keep a Changelog](https://keepachangelog.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
