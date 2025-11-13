# KATO Version Management

## Overview

KATO follows [Semantic Versioning 2.0.0](https://semver.org/) for all releases. This document provides detailed guidance on version management, branching strategies, and version consistency.

## Table of Contents
1. [Semantic Versioning](#semantic-versioning)
2. [Version Consistency](#version-consistency)
3. [Branching Strategy](#branching-strategy)
4. [Pre-Release Versions](#pre-release-versions)
5. [Version Metadata](#version-metadata)
6. [Deprecation Policy](#deprecation-policy)

## Semantic Versioning

### Format

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

**Examples:**
- `3.0.0` - Major release
- `3.1.0` - Minor release
- `3.1.1` - Patch release
- `3.2.0-beta.1` - Pre-release
- `3.2.0+20251113` - With build metadata

### Version Components

#### MAJOR Version

Increment when making **incompatible API changes**.

**Breaking Changes Include:**
- Removing API endpoints
- Changing request/response schemas (incompatibly)
- Removing configuration options
- Changing default behavior significantly
- Database migrations required
- Dependency version bumps (major)

**Decision Tree:**
```
Will existing clients break without code changes?
  ├─ YES → MAJOR version bump
  └─ NO  → Check MINOR/PATCH
```

**Examples:**
```python
# v2.x → v3.0 (MAJOR)
# REMOVED: /observe endpoint (moved to /sessions/{id}/observe)
# OLD: POST /observe
# NEW: POST /sessions/{session_id}/observe

# v3.x → v4.0 (MAJOR)
# CHANGED: emotives field now required
# OLD: emotives optional in observe request
# NEW: emotives required (breaking change)
```

#### MINOR Version

Increment when adding **functionality in backward-compatible manner**.

**New Features Include:**
- Adding new API endpoints
- Adding optional parameters
- Adding new configuration options (with defaults)
- Performance improvements
- New capabilities
- Deprecating features (not removing)

**Decision Tree:**
```
Does this add new functionality?
  ├─ YES → Is it backward compatible?
  │         ├─ YES → MINOR version bump
  │         └─ NO  → MAJOR version bump
  └─ NO  → PATCH version bump
```

**Examples:**
```python
# v3.0.0 → v3.1.0 (MINOR)
# ADDED: New /metrics endpoint
POST /sessions/{session_id}/metrics

# v3.1.0 → v3.2.0 (MINOR)
# ADDED: Optional 'priority' field in observe request
POST /sessions/{session_id}/observe
{
  "strings": [...],
  "priority": 1  # NEW, OPTIONAL
}
```

#### PATCH Version

Increment for **backward-compatible bug fixes**.

**Bug Fixes Include:**
- Fixing incorrect behavior
- Security patches
- Documentation updates
- Performance fixes (no API changes)
- Dependency updates (patch level)

**Decision Tree:**
```
Does this fix a bug without changing functionality?
  ├─ YES → PATCH version bump
  └─ NO  → Check MINOR/MAJOR
```

**Examples:**
```python
# v3.1.0 → v3.1.1 (PATCH)
# FIXED: Pattern matching returned duplicates

# v3.1.1 → v3.1.2 (PATCH)
# FIXED: Memory leak in session cleanup
```

## Version Consistency

### Source of Truth

**Primary:** `pyproject.toml`
```toml
[tool.poetry]
name = "kato"
version = "3.0.0"
```

**Synced Files:**
1. `setup.py`
2. `kato/__init__.py`
3. Git tags (`v3.0.0`)
4. Container images (`ghcr.io/sevakavakians/kato:3.0.0`)

### Version Update Script

```bash
#!/bin/bash
# bump-version.sh ensures consistency

NEW_VERSION=$1

# Update pyproject.toml
sed -i '' "s/^version = .*/version = \"$NEW_VERSION\"/" pyproject.toml

# Update setup.py
sed -i '' "s/version=.*/version=\"$NEW_VERSION\",/" setup.py

# Update __init__.py
sed -i '' "s/__version__ = .*/__version__ = '$NEW_VERSION'/" kato/__init__.py

echo "Updated version to $NEW_VERSION"
```

### Verification

```bash
# Verify version consistency
VERSION=$(grep 'version =' pyproject.toml | cut -d'"' -f2)
echo "pyproject.toml: $VERSION"

VERSION=$(grep 'version=' setup.py | cut -d'"' -f2)
echo "setup.py: $VERSION"

VERSION=$(python -c "import kato; print(kato.__version__)")
echo "kato.__version__: $VERSION"

VERSION=$(git describe --tags --abbrev=0)
echo "Git tag: $VERSION"
```

## Branching Strategy

### Main Branch

- **Branch:** `main`
- **Purpose:** Production-ready code
- **Protection:** Requires PR approval
- **Releases:** Tagged from main

### Development Workflow

```
main (stable)
  ↓
feature/new-endpoint → PR → main → tag v3.1.0
  ↓
bugfix/fix-memory-leak → PR → main → tag v3.0.1
  ↓
hotfix/critical-fix → PR → main → tag v3.0.2
```

### Branch Naming

```bash
# Features (MINOR bump)
git checkout -b feature/add-metrics-endpoint

# Bug fixes (PATCH bump)
git checkout -b bugfix/fix-session-ttl

# Hotfixes (PATCH bump)
git checkout -b hotfix/critical-memory-leak

# Major changes (MAJOR bump)
git checkout -b major/remove-deprecated-api
```

### Hotfix Workflow

```bash
# Scenario: Critical bug in production (v3.0.1)
# Main branch has unreleased changes

# 1. Create hotfix from release tag
git checkout -b hotfix/3.0.2 v3.0.1

# 2. Fix bug
git commit -m "fix: critical bug"

# 3. Bump version
./bump-version.sh 3.0.2

# 4. Tag
git tag -a v3.0.2 -m "Hotfix: critical bug"
git push origin hotfix/3.0.2
git push origin v3.0.2

# 5. Merge to main
git checkout main
git merge hotfix/3.0.2
git push origin main

# 6. Cleanup
git branch -d hotfix/3.0.2
```

## Pre-Release Versions

### Format

```
MAJOR.MINOR.PATCH-PRERELEASE.ITERATION
```

**Types:**
- `alpha` - Early testing
- `beta` - Feature complete, testing
- `rc` - Release candidate

**Examples:**
- `3.1.0-alpha.1`
- `3.1.0-beta.1`
- `3.1.0-rc.1`

### Creating Pre-Releases

```bash
# Alpha release
./bump-version.sh 3.1.0-alpha.1

# Beta release
./bump-version.sh 3.1.0-beta.1

# Release candidate
./bump-version.sh 3.1.0-rc.1

# Final release
./bump-version.sh 3.1.0
```

### Pre-Release Workflow

```bash
# 1. Create pre-release
git checkout -b release/3.1.0
./bump-version.sh 3.1.0-beta.1
git commit -m "chore: release v3.1.0-beta.1"
git tag -a v3.1.0-beta.1 -m "Beta release"
git push origin release/3.1.0
git push origin v3.1.0-beta.1

# 2. Test thoroughly

# 3. Release final version
./bump-version.sh 3.1.0
git commit -m "chore: release v3.1.0"
git tag -a v3.1.0 -m "Release v3.1.0"
git push origin release/3.1.0
git push origin v3.1.0

# 4. Merge to main
git checkout main
git merge release/3.1.0
git push origin main
```

### Container Tags

Pre-releases **do not** update `:latest` tag:

```bash
# Pre-release builds
ghcr.io/sevakavakians/kato:3.1.0-beta.1    # Specific pre-release
# (does NOT update :latest, :3.1, or :3)

# Final release builds
ghcr.io/sevakavakians/kato:3.1.0           # Specific version
ghcr.io/sevakavakians/kato:3.1             # Minor version
ghcr.io/sevakavakians/kato:3               # Major version
ghcr.io/sevakavakians/kato:latest          # Latest stable
```

## Version Metadata

### Build Metadata

Optional metadata after `+`:

```
3.1.0+20251113
3.1.0+git.abc123
3.1.0+build.42
```

**Not included in version precedence.**

### Reading Version at Runtime

```python
import kato

# Get version string
print(kato.__version__)  # "3.1.0"

# Parse version
from packaging.version import Version
v = Version(kato.__version__)
print(f"Major: {v.major}")  # 3
print(f"Minor: {v.minor}")  # 1
print(f"Patch: {v.micro}")  # 0
```

### Container Labels

```dockerfile
LABEL org.opencontainers.image.version="3.1.0"
LABEL org.opencontainers.image.created="2025-11-13T10:00:00Z"
LABEL org.opencontainers.image.revision="abc123"
```

```bash
# Inspect container version
docker inspect ghcr.io/sevakavakians/kato:latest | \
  jq '.[0].Config.Labels["org.opencontainers.image.version"]'
```

## Deprecation Policy

### Deprecation Process

1. **Announce:** Deprecation notice in release notes
2. **Warning:** Add deprecation warnings to code
3. **Timeline:** Minimum 1 MAJOR version before removal
4. **Remove:** Remove in next MAJOR version

### Example Deprecation

```python
# v3.0.0 - Deprecate endpoint
@app.post("/observe")  # Deprecated
@deprecated(
    "Use /sessions/{session_id}/observe instead. "
    "This endpoint will be removed in v4.0.0"
)
def observe_deprecated():
    warnings.warn(
        "Deprecated: Use /sessions/{session_id}/observe",
        DeprecationWarning
    )
    # ... implementation ...

# v4.0.0 - Remove deprecated endpoint
# (removed)
```

### Deprecation Timeline

```
v3.0.0 - Deprecate /observe endpoint
  ├─ Add deprecation warning
  ├─ Update documentation
  └─ Announce in CHANGELOG

v3.1.0 - (still available with warning)
v3.2.0 - (still available with warning)

v4.0.0 - Remove /observe endpoint
  ├─ Breaking change
  └─ Migration guide provided
```

## Version Comparison

### Precedence Rules

```
1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta < 1.0.0-rc < 1.0.0
```

```python
from packaging.version import Version

versions = [
    "1.0.0",
    "1.0.0-beta.1",
    "1.0.0-alpha",
    "1.0.0-rc.1"
]

sorted_versions = sorted(versions, key=Version)
print(sorted_versions)
# ['1.0.0-alpha', '1.0.0-beta.1', '1.0.0-rc.1', '1.0.0']
```

## Best Practices

1. **Never reuse versions** - Each version is immutable
2. **Tag immediately** - Tag releases as soon as version is bumped
3. **Automate checks** - CI validates version consistency
4. **Document breaking changes** - Clear migration guides
5. **Test upgrades** - Test upgrading from previous versions
6. **Communicate early** - Announce deprecations in advance
7. **Version everything** - APIs, schemas, container images
8. **Follow conventions** - Use conventional commits

## Related Documentation

- [Release Process](releasing.md)
- [Changelog Guidelines](changelog-guidelines.md)
- [Semantic Versioning Specification](https://semver.org/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
