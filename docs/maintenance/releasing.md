# KATO Release Process

## Overview

This document expands on the [root RELEASING.md](/RELEASING.md) with additional maintainer guidance, automation details, and best practices.

For quick reference, see:
- **[RELEASING.md (Root)](/RELEASING.md)** - Quick start and automated release workflow
- **[Container Manager Agent](/docs/CONTAINER_MANAGER.md)** - Automated version detection

## Table of Contents
1. [Release Workflow](#release-workflow)
2. [Version Bump Criteria](#version-bump-criteria)
3. [Pre-Release Checklist](#pre-release-checklist)
4. [Automated Release](#automated-release)
5. [Manual Release](#manual-release)
6. [Post-Release Tasks](#post-release-tasks)
7. [Hotfix Process](#hotfix-process)
8. [Rollback Procedure](#rollback-procedure)

## Release Workflow

### Standard Release Cycle

```
1. Development → 2. Feature Complete → 3. Testing → 4. Release → 5. Monitoring
     ↓                   ↓                  ↓            ↓           ↓
  main branch      Feature freeze    All tests pass   Tag & build  Track metrics
```

### Release Timeline

- **Patch releases**: As needed for bug fixes (no schedule)
- **Minor releases**: When significant features are complete
- **Major releases**: Breaking changes or major milestones

## Version Bump Criteria

### MAJOR Version (X.0.0)

Increment when making **incompatible API changes**:

✅ **Examples requiring MAJOR bump:**
- Remove or rename API endpoints
- Change request/response schemas (breaking)
- Remove configuration parameters
- Change core algorithms affecting behavior
- Database schema changes requiring migration
- Modify session management incompatibly

```python
# Breaking change example
# OLD API (v2.x)
POST /observe
{"strings": [...], "vectors": [...]}

# NEW API (v3.0) - Breaking change
POST /sessions/{session_id}/observe
{"strings": [...], "vectors": [...], "emotives": {...}}  # emotives now required
```

### MINOR Version (x.Y.0)

Increment when adding **functionality in backward-compatible manner**:

✅ **Examples requiring MINOR bump:**
- Add new API endpoints
- Add new configuration options (with defaults)
- Add new features
- Performance improvements
- Deprecate features (with warnings, not removal)
- Add optional request/response fields

```python
# Backward-compatible addition
# v2.1.0 - New endpoint, old endpoints still work
POST /sessions/{session_id}/learn   # NEW
POST /sessions/{session_id}/observe # Still works
```

### PATCH Version (x.y.Z)

Increment for **backward-compatible bug fixes**:

✅ **Examples requiring PATCH bump:**
- Fix bugs
- Security patches
- Documentation updates
- Code cleanup/refactoring
- Test improvements
- Dependency updates (no functionality change)

```python
# Bug fix example - v2.0.1
# Fixed: Pattern matching returned duplicates
# No API changes, just internal fix
```

## Pre-Release Checklist

Before releasing, ensure:

### Code Quality
- [ ] All tests pass: `./run_tests.sh --no-start --no-stop`
- [ ] No linting errors: `ruff check kato/`
- [ ] Code coverage acceptable (>80%)
- [ ] No security vulnerabilities: `pip-audit`

### Documentation
- [ ] CHANGELOG.md updated with all changes
- [ ] API documentation reflects changes
- [ ] README.md updated if needed
- [ ] Migration guide written (for breaking changes)

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] API tests pass
- [ ] Performance tests pass
- [ ] Manual smoke testing complete

### Repository
- [ ] All changes committed
- [ ] On `main` branch
- [ ] Local branch up to date: `git pull origin main`
- [ ] No uncommitted changes: `git status`

### Communication
- [ ] Team notified of pending release
- [ ] Breaking changes communicated clearly
- [ ] Release notes drafted

## Automated Release

### Using Container Manager Agent (Recommended)

The container-manager agent analyzes git history to determine appropriate version bump.

**Workflow:**
```bash
# 1. Ensure all changes are committed
git status

# 2. Ask Claude Code to release
"I've completed the bug fixes. Please release a new version."

# Claude Code will:
# - Analyze git commits since last version
# - Determine bump type (patch/minor/major)
# - Run container-manager.sh with appropriate version
# - Build and push container images
# - Create git tag
```

**What the agent analyzes:**
- Commit messages (conventional commits format)
- Files changed (API files = potential breaking change)
- Nature of changes (adds vs removes vs modifies)
- Test changes
- Documentation updates

### Manual Invocation

```bash
# Patch release (bug fixes)
./container-manager.sh patch "Fix pattern matching bug"

# Minor release (new features)
./container-manager.sh minor "Add new /metrics endpoint"

# Major release (breaking changes)
./container-manager.sh major "Remove deprecated API v1 endpoints"
```

## Manual Release

If you need full control over the release process:

### Step 1: Update Version Numbers

```bash
# Use bump-version.sh
./bump-version.sh patch "Bug fixes"

# Or manually edit:
# - pyproject.toml
# - setup.py
# - kato/__init__.py
```

### Step 2: Update CHANGELOG

Move `[Unreleased]` entries to new version section:

```markdown
## [Unreleased]

## [3.0.1] - 2025-11-13

### Fixed
- Pattern matching duplicate results
- Session TTL not extending properly

### Changed
- Optimized Redis connection pooling
```

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v3.0.1"
```

### Step 3: Create Git Tag

```bash
# Create annotated tag
git tag -a v3.0.1 -m "Release v3.0.1: Bug fixes and optimizations"

# Verify tag
git show v3.0.1
```

### Step 4: Push to GitHub

```bash
# Push commits
git push origin main

# Push tag
git push origin v3.0.1
```

### Step 5: Build and Push Container

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u sevakavakians --password-stdin

# Build and push with multi-tag strategy
./build-and-push.sh

# Verify
docker pull ghcr.io/sevakavakians/kato:3.0.1
docker pull ghcr.io/sevakavakians/kato:latest
```

### Step 6: Create GitHub Release

1. Go to https://github.com/sevakavakians/kato/releases
2. Click "Draft a new release"
3. Select tag: `v3.0.1`
4. Release title: `KATO v3.0.1`
5. Description: Copy from CHANGELOG.md
6. Publish release

## Post-Release Tasks

### Verification

```bash
# 1. Verify container images exist
docker pull ghcr.io/sevakavakians/kato:3.0.1
docker pull ghcr.io/sevakavakians/kato:3
docker pull ghcr.io/sevakavakians/kato:latest

# 2. Verify version in container
docker run --rm ghcr.io/sevakavakians/kato:3.0.1 \
  python -c "import kato; print(kato.__version__)"

# 3. Test container starts correctly
docker run --rm -p 8000:8000 ghcr.io/sevakavakians/kato:3.0.1 &
sleep 5
curl http://localhost:8000/health

# 4. Verify GitHub release exists
curl -s https://api.github.com/repos/sevakavakians/kato/releases/latest | jq .tag_name
```

### Communication

- [ ] Announce release in team channels
- [ ] Update public documentation sites
- [ ] Send notification to users (for major/minor)
- [ ] Update Docker Hub description (if applicable)

### Monitoring

- [ ] Monitor error rates in production
- [ ] Track deployment success rate
- [ ] Watch for GitHub issues reporting problems
- [ ] Monitor Docker pull metrics

## Hotfix Process

For critical bugs in production:

### Option 1: Hotfix from Main (Recommended)

If `main` branch is stable:

```bash
# 1. Fix bug on main
git checkout main
# ... make fixes ...
git commit -m "fix: critical bug in pattern matching"

# 2. Release patch version
./container-manager.sh patch "Critical bug fix"

# 3. Verify fix
# ... test thoroughly ...
```

### Option 2: Hotfix Branch

If `main` has unreleased changes:

```bash
# 1. Create hotfix branch from last release
git checkout -b hotfix/3.0.2 v3.0.1

# 2. Make fixes
# ... fix bug ...
git commit -m "fix: critical bug"

# 3. Bump version
./bump-version.sh patch "Hotfix: Critical bug"

# 4. Tag and push
git tag -a v3.0.2 -m "Hotfix: Critical bug fix"
git push origin hotfix/3.0.2
git push origin v3.0.2

# 5. Build and deploy
./build-and-push.sh

# 6. Merge back to main
git checkout main
git merge hotfix/3.0.2
git push origin main

# 7. Cleanup
git branch -d hotfix/3.0.2
git push origin --delete hotfix/3.0.2
```

## Rollback Procedure

If a release has critical issues:

### Container Rollback

```bash
# 1. Identify last good version
docker images ghcr.io/sevakavakians/kato

# 2. Redeploy last good version
docker pull ghcr.io/sevakavakians/kato:3.0.0
docker tag ghcr.io/sevakavakians/kato:3.0.0 \
           ghcr.io/sevakavakians/kato:latest
docker push ghcr.io/sevakavakians/kato:latest

# 3. Update deployments
# Kubernetes: kubectl set image deployment/kato kato=ghcr.io/sevakavakians/kato:3.0.0
# Docker Compose: update docker-compose.yml and restart
```

### Git Rollback

```bash
# Option 1: Revert commit (preferred)
git revert v3.0.1
git push origin main

# Option 2: Delete tag (if not deployed)
git tag -d v3.0.1
git push origin --delete v3.0.1
```

### Communication

```markdown
**Rollback Notice: KATO v3.0.1**

We've rolled back v3.0.1 due to [issue description].

**Action Required:**
- If you deployed v3.0.1, rollback to v3.0.0
- Command: docker pull ghcr.io/sevakavakians/kato:3.0.0

**Status:** Investigating issue, fix expected in v3.0.2

**Questions:** Contact team at ...
```

## Release Checklist Template

Copy this for each release:

```markdown
## Release Checklist: KATO vX.Y.Z

### Pre-Release
- [ ] All tests pass
- [ ] Code linted and formatted
- [ ] CHANGELOG.md updated
- [ ] Documentation updated
- [ ] Security scan clean
- [ ] Team notified

### Release
- [ ] Version bumped (pyproject.toml, setup.py, __init__.py)
- [ ] Git tag created
- [ ] Changes pushed to GitHub
- [ ] Container built and pushed
- [ ] GitHub release created
- [ ] Release notes published

### Post-Release
- [ ] Container verified (docker pull)
- [ ] Version verified (python -c "import kato...")
- [ ] Health check passes
- [ ] Team notified
- [ ] Monitoring active
- [ ] Documentation updated
```

## Related Documentation

- **[RELEASING.md (Root)](/RELEASING.md)** - Quick start guide
- [Version Management](version-management.md) - Semantic versioning details
- [Changelog Guidelines](changelog-guidelines.md) - Writing changelogs
- [Container Manager](/docs/CONTAINER_MANAGER.md) - Automation details

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
