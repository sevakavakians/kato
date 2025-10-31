# Container Manager Agent

The **container-manager** agent is a specialized agent responsible for version management and container image publishing after code changes. It ensures consistent versioning across all files and automates the release process.

## Table of Contents

- [Overview](#overview)
- [When to Use](#when-to-use)
- [What It Does](#what-it-does)
- [Usage Methods](#usage-methods)
- [Version Bump Rules](#version-bump-rules)
- [Prerequisites](#prerequisites)
- [Workflow](#workflow)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Overview

The container-manager agent automates the entire release pipeline:
1. ✅ Version consistency across all files
2. ✅ Git commit and tagging
3. ✅ Container image building with proper tags
4. ✅ Pushing to GitHub Container Registry (ghcr.io)
5. ✅ Verification and summary

**Key Benefits:**
- Prevents version inconsistencies
- Ensures proper semantic versioning
- Automates repetitive release tasks
- Reduces human error
- Maintains release discipline

---

## When to Use

Invoke the container-manager agent after code changes are committed and ready for release. The agent will **automatically determine** the appropriate version bump type based on the nature of changes.

### ✅ Always Use After:

1. **Bug Fixes** → Agent determines `patch` bump
   - Fixed a bug in pattern matching
   - Security patch
   - Documentation fixes
   - Performance improvements (non-breaking)

2. **New Features** → Agent determines `minor` bump
   - Added new API endpoint
   - New functionality
   - New configuration options
   - Backward-compatible changes

3. **Breaking Changes** → Agent determines `major` bump
   - API endpoint removal or incompatible changes
   - Architecture changes requiring migration
   - Removal of deprecated features
   - Database schema changes

### ❌ Do NOT Use For:

- Work in progress (WIP) commits
- Experimental code not ready for release
- Changes that don't affect functionality (comments, formatting)
- Pre-merge commits on feature branches

### 🤖 Automatic Version Detection

**When using with Claude Code or project-manager**, the agent analyzes:
1. **Git commit messages** - Following Conventional Commits format
2. **Files changed** - Significance of modified files
3. **Diff analysis** - Nature of code changes (breaking vs additive vs fixes)
4. **User context** - Description provided

The agent then determines whether the changes constitute a major, minor, or patch release and proceeds accordingly.

**When using manually**, you specify the bump type:
```bash
./container-manager.sh patch "Fix pattern matching bug"
```

---

## What It Does

The container-manager performs these steps automatically:

### Step 1: Version Bump
- Reads current version from `pyproject.toml`
- Increments version based on bump type (major/minor/patch)
- Updates version in:
  - `pyproject.toml`
  - `setup.py`
  - `kato/__init__.py`

### Step 2: Git Operations
- Commits version changes with message: `chore: bump version to X.Y.Z`
- Creates annotated git tag: `vX.Y.Z`
- Pushes commit and tag to remote

### Step 3: Container Build
- Builds Docker image with version metadata
- Creates multiple tags:
  - `ghcr.io/sevakavakians/kato:X.Y.Z` (specific version)
  - `ghcr.io/sevakavakians/kato:X.Y` (minor version)
  - `ghcr.io/sevakavakians/kato:X` (major version)
  - `ghcr.io/sevakavakians/kato:latest` (latest stable)

### Step 4: Push to Registry
- Pushes all image tags to GitHub Container Registry
- Verifies image availability

### Step 5: Summary
- Displays complete summary
- Provides next steps
- Shows commands for users to pull new version

---

## Usage Methods

### Method 1: Using the Task Tool (Recommended for Claude Code)

When working in Claude Code, use the Task tool to invoke the container-manager agent:

```
User: "I've fixed the pattern matching bug. Please release a patch version."

Claude: I'll trigger the container-manager agent to handle the release.
<uses Task tool with subagent_type="container-manager">
<prompt>
Release a patch version for the pattern matching bug fix.

Bump type: patch
Description: Fix pattern matching bug in similarity calculations

The code changes have already been committed to main branch.
Please proceed with version bump, tagging, and container image publishing.
</prompt>
</uses>
```

### Method 2: Direct Script Execution

For manual execution or CI/CD pipelines:

```bash
# Patch version (bug fixes)
./container-manager.sh patch "Fix pattern matching bug"

# Minor version (new features)
./container-manager.sh minor "Add WebSocket support"

# Major version (breaking changes)
./container-manager.sh major "Redesign API endpoints"
```

### Method 3: Automated Mode (CI/CD)

For non-interactive environments:

```bash
# Set AUTO_MODE to skip prompts
export AUTO_MODE=true
./container-manager.sh patch "Automated security patch"
```

---

## Version Bump Rules

Follow [Semantic Versioning 2.0.0](https://semver.org/):

### How the Agent Determines Version Bump

When invoked by Claude Code or project-manager, the agent analyzes changes using these criteria:

#### 1. Git Commit Analysis
- Checks commits since last version tag
- Follows Conventional Commits format:
  - `fix:`, `perf:`, `docs:`, `refactor:`, `test:` → **patch**
  - `feat:` → **minor**
  - `BREAKING CHANGE:` or `!` suffix → **major**

#### 2. File Change Analysis

**MAJOR indicators (breaking changes):**
- API endpoint paths changed/removed in `kato/api/endpoints/`
- Database schema changes in `kato/storage/`
- Removal of public functions/classes
- Function signature changes that break compatibility
- Required new environment variables

**MINOR indicators (new features):**
- New API endpoints in `kato/api/endpoints/`
- New modules in `kato/gpu/`, `kato/workers/`, etc.
- New configuration options (optional/defaulted)
- New public functions/classes

**PATCH indicators (fixes/improvements):**
- Bug fixes in existing code
- Performance optimizations
- Documentation updates in `docs/`
- Test improvements in `tests/`
- Internal refactoring

#### 3. Decision Tree

```
Did any change break backward compatibility?
├─ YES → MAJOR (X.Y.Z → X+1.0.0)
└─ NO → Did any change add new functionality?
    ├─ YES → MINOR (X.Y.Z → X.Y+1.0)
    └─ NO → Are changes only fixes/improvements?
        ├─ YES → PATCH (X.Y.Z → X.Y.Z+1)
        └─ UNCLEAR → Agent asks for clarification
```

### PATCH (X.Y.Z → X.Y.Z+1)

**Automatic detection when:**
- Bug fixes in existing code
- Security patches
- Documentation updates
- Performance improvements (non-breaking)
- Internal refactoring (no API changes)

**Example:** `2.0.0` → `2.0.1`

**Example changes:**
- Fixed pattern matching calculation bug
- Optimized MongoDB query performance
- Updated README documentation
- Fixed test flakiness

### MINOR (X.Y.Z → X.Y+1.0)

**Automatic detection when:**
- New features (backward-compatible)
- New API endpoints
- New configuration options (optional)
- Deprecation warnings (not removal)
- Substantial improvements

**Example:** `2.0.1` → `2.1.0`

**Example changes:**
- Added `/metrics` endpoint
- Added GPU acceleration support
- Added WebSocket notifications
- Added new session auto-extension feature

### MAJOR (X.Y.Z → X+1.0.0)

**Automatic detection when:**
- Breaking API changes
- Removal of deprecated features
- Incompatible architecture changes
- Database schema changes requiring migration
- Required new environment variables

**Example:** `2.1.3` → `3.0.0`

**Example changes:**
- Removed deprecated `/observe-direct` endpoint
- Changed response format for `/sessions` API
- Required new `REDIS_URL` environment variable
- Changed function signature: `observe(strings)` → `observe(data)`

---

## Prerequisites

### Before First Use:

1. **Docker Authentication:**
   ```bash
   # Login to GitHub Container Registry
   echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
   ```

   Get a token at: https://github.com/settings/tokens
   Required scopes: `write:packages`, `read:packages`

2. **Git Configuration:**
   ```bash
   # Ensure git is configured
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```

3. **Docker Running:**
   ```bash
   # Verify Docker is running
   docker info
   ```

4. **Clean Working Directory:**
   ```bash
   # Commit or stash all changes
   git status
   ```

---

## Workflow

### Standard Release Workflow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Developer makes code changes                         │
│    - Fix bugs, add features, etc.                       │
│    - Test thoroughly                                     │
│    - Commit to main branch                              │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 2. Invoke container-manager agent                       │
│    - Specify bump type (major/minor/patch)              │
│    - Provide description                                 │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 3. Agent bumps version                                  │
│    - Updates pyproject.toml, setup.py, __init__.py     │
│    - Creates git commit: "chore: bump version to X.Y.Z" │
│    - Creates git tag: vX.Y.Z                            │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 4. Agent pushes to remote                               │
│    - git push origin main                               │
│    - git push origin vX.Y.Z                             │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 5. Agent builds container images                        │
│    - Builds with version metadata                       │
│    - Creates multiple tags (X.Y.Z, X.Y, X, latest)      │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 6. Agent pushes to ghcr.io                              │
│    - Pushes all tags                                    │
│    - Verifies availability                              │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ 7. Release complete!                                    │
│    - Version updated                                    │
│    - Images available for users                         │
│    - Create GitHub release (optional)                   │
└─────────────────────────────────────────────────────────┘
```

---

## Examples

### Example 1: Bug Fix Release

**Scenario:** Fixed a bug in pattern similarity calculations

```bash
# All changes committed to main branch
git status  # Clean working directory

# Invoke container-manager
./container-manager.sh patch "Fix similarity calculation bug"

# Output:
# ✓ Version bumped: 2.0.0 → 2.0.1
# ✓ Git tag created: v2.0.1
# ✓ Changes pushed to remote
# ✓ Container images built and pushed
#   - ghcr.io/sevakavakians/kato:2.0.1
#   - ghcr.io/sevakavakians/kato:2.0
#   - ghcr.io/sevakavakians/kato:2
#   - ghcr.io/sevakavakians/kato:latest
```

### Example 2: New Feature Release

**Scenario:** Added GPU acceleration support

```bash
# All changes committed to main branch

# Invoke container-manager
./container-manager.sh minor "Add GPU acceleration support"

# Output:
# ✓ Version bumped: 2.0.1 → 2.1.0
# ✓ Git tag created: v2.1.0
# ✓ Changes pushed to remote
# ✓ Container images built and pushed
```

### Example 3: Breaking Change Release

**Scenario:** Redesigned API endpoints (breaking changes)

```bash
# All changes committed to main branch

# Invoke container-manager
./container-manager.sh major "Redesign API endpoints with breaking changes"

# Output:
# ✓ Version bumped: 2.1.0 → 3.0.0
# ✓ Git tag created: v3.0.0
# ✓ Changes pushed to remote
# ✓ Container images built and pushed
```

### Example 4: Using with Claude Code (Automatic Version Detection)

```
User: I've added a new /metrics endpoint to the API. Can you release a new version?

Claude Code: Let me analyze the changes and determine the appropriate version bump.

<runs analysis>
git log --oneline v2.0.0..HEAD
> feat: Add /metrics endpoint for system monitoring
> test: Add tests for metrics endpoint

git diff --name-only v2.0.0..HEAD
> kato/api/endpoints/kato_ops.py
> tests/tests/api/test_metrics_endpoint.py

Analysis:
- New feature added (new API endpoint)
- Backward compatible (no breaking changes)
- Conventional commit shows "feat:"
→ Determination: MINOR version bump

Claude Code: I'll use the container-manager agent to release version 2.1.0 with the new metrics endpoint.

<invokes Task tool>
subagent_type: container-manager
prompt: Release a new version for the /metrics endpoint feature.

Analysis of changes:
- Added new /metrics endpoint in kato/api/endpoints/kato_ops.py
- Added comprehensive tests
- Conventional commit: "feat: Add /metrics endpoint"
- Files changed: API endpoints (additive only)
- No breaking changes detected

Recommended bump type: minor (2.0.0 → 2.1.0)
Description: Add /metrics endpoint for system monitoring

Please proceed with version bump, git operations, and container image publishing.

<agent completes>

Claude Code: Release complete! Version 2.1.0 is now available.
- Version bump: 2.0.0 → 2.1.0 (minor - new feature)
- Git tag: v2.1.0 pushed to remote
- Container images built and pushed:
  - ghcr.io/sevakavakians/kato:2.1.0
  - ghcr.io/sevakavakians/kato:2.1
  - ghcr.io/sevakavakians/kato:2
  - ghcr.io/sevakavakians/kato:latest

Users can now pull the new version with:
  docker pull ghcr.io/sevakavakians/kato:2.1.0
```

**Key Point:** Notice the user didn't specify "minor version" - Claude Code analyzed the changes and automatically determined it should be a minor version bump based on the nature of the changes (new feature, backward compatible).

---

## Troubleshooting

### Problem: "Error: Uncommitted changes"

**Cause:** Working directory has uncommitted files

**Solution:**
```bash
# Option 1: Commit changes
git add .
git commit -m "Your commit message"

# Option 2: Stash changes
git stash

# Then run container-manager again
./container-manager.sh patch "Description"
```

### Problem: "Error: Docker is not running"

**Cause:** Docker daemon not started

**Solution:**
```bash
# macOS/Windows: Start Docker Desktop
# Linux: Start Docker service
sudo systemctl start docker

# Verify
docker info
```

### Problem: "Error: Authentication failed for ghcr.io"

**Cause:** Not logged into GitHub Container Registry

**Solution:**
```bash
# Create GitHub personal access token with write:packages scope
# Then login:
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

### Problem: "Error: Not on main branch"

**Cause:** Currently on a feature branch, not main

**Solution:**
```bash
# Option 1: Merge to main first
git checkout main
git merge your-feature-branch
./container-manager.sh patch "Description"

# Option 2: Force run on current branch (not recommended)
# Edit container-manager.sh to allow other branches
```

### Problem: "Error: Tag already exists"

**Cause:** Version tag already exists in git

**Solution:**
```bash
# Check existing tags
git tag -l

# If tag was created by mistake, delete it:
git tag -d v2.0.1                # Delete locally
git push origin --delete v2.0.1   # Delete remotely

# Then run container-manager again
./container-manager.sh patch "Description"
```

### Problem: Image build fails

**Cause:** Dockerfile errors or missing dependencies

**Solution:**
```bash
# Test build manually first
docker build -t test-image .

# Check Docker logs
docker logs <container-id>

# Fix issues in Dockerfile, then run container-manager again
```

### Problem: "Could not verify image"

**Cause:** Registry propagation delay or network issues

**Solution:**
```bash
# Wait a few minutes, then verify manually:
docker manifest inspect ghcr.io/sevakavakians/kato:2.0.1

# If still not available, check GitHub Packages:
# https://github.com/sevakavakians/kato/pkgs/container/kato

# Check build logs for errors
docker build --progress=plain -t test .
```

---

## Best Practices

### 1. Release Frequency

- **Patch releases**: As soon as critical bugs are fixed
- **Minor releases**: Every 2-4 weeks for feature batches
- **Major releases**: When necessary, with proper planning and migration guides

### 2. Pre-Release Checklist

Before invoking container-manager:

- [ ] All tests pass (`./run_tests.sh`)
- [ ] Code is linted (`ruff check kato/`)
- [ ] Documentation is updated
- [ ] CHANGELOG.md has unreleased changes documented
- [ ] All changes are committed
- [ ] On main branch (or appropriate release branch)

### 3. Post-Release Tasks

After container-manager completes:

- [ ] Update CHANGELOG.md (move unreleased to new version)
- [ ] Create GitHub release with notes
- [ ] Update deployment documentation if needed
- [ ] Notify users (if major version)
- [ ] Update example code/tutorials

### 4. Version Discipline

- Never skip versions (2.0.0 → 2.0.2 ❌)
- Never go backward (2.1.0 → 2.0.9 ❌)
- Follow semantic versioning strictly
- Document breaking changes clearly

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Release Container

on:
  workflow_dispatch:
    inputs:
      bump_type:
        description: 'Version bump type'
        required: true
        type: choice
        options:
          - patch
          - minor
          - major
      description:
        description: 'Release description'
        required: true
        type: string

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Run Container Manager
        env:
          AUTO_MODE: true
        run: |
          ./container-manager.sh ${{ inputs.bump_type }} "${{ inputs.description }}"
```

---

## Additional Resources

- [Semantic Versioning 2.0.0](https://semver.org/)
- [RELEASING.md](../RELEASING.md) - Manual release process
- [CHANGELOG.md](../CHANGELOG.md) - Version history
- [build-and-push.sh](../build-and-push.sh) - Build script
- [bump-version.sh](../bump-version.sh) - Version bump script

---

## Support

For issues with the container-manager agent:

1. Check this documentation first
2. Review [RELEASING.md](../RELEASING.md) for manual alternatives
3. Check GitHub Issues: https://github.com/sevakavakians/kato/issues
4. Verify Docker and git configuration

For general KATO questions:
- Documentation: http://localhost:8000/docs (when running)
- Repository: https://github.com/sevakavakians/kato
