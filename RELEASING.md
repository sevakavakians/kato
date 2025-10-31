# KATO Release Process

This document describes the release process for KATO, including versioning, container image builds, and publishing.

## Quick Start: Automated Release

**⚡ Fastest Way:** Use the **container-manager** agent for fully automated releases with intelligent version detection:

### Using with Claude Code (Recommended)

Simply tell Claude Code you want to release, and it will analyze the changes to determine the appropriate version bump:

```
User: "I've fixed the pattern matching bug. Please release a new version."

Claude Code analyzes:
- Git commits since last version
- Files changed and their significance
- Nature of changes (breaking/additive/fixes)

Determines: PATCH version (bug fix, no breaking changes)
→ Releases version 2.0.1 automatically
```

**Examples:**

| What You Say | Agent Determines | Result |
|--------------|------------------|--------|
| "Fixed bug in pattern search" | PATCH | 2.0.0 → 2.0.1 |
| "Added new /metrics endpoint" | MINOR | 2.0.1 → 2.1.0 |
| "Removed deprecated API endpoints" | MAJOR | 2.1.0 → 3.0.0 |
| "Optimized database queries" | PATCH | 2.0.0 → 2.0.1 |
| "Added GPU acceleration support" | MINOR | 2.0.1 → 2.1.0 |

### Manual CLI Usage

For direct script execution (you specify the bump type):

```bash
./container-manager.sh patch "Fix pattern matching bug"
./container-manager.sh minor "Add new API endpoint"
./container-manager.sh major "Breaking API changes"
```

**Benefits:**
- ✅ **Automatic version determination** - No need to specify major/minor/patch
- ✅ Automatic version consistency across all files
- ✅ Creates git commits and tags
- ✅ Builds and pushes container images
- ✅ Handles multi-tag strategy (X.Y.Z, X.Y, X, latest)
- ✅ Verifies deployment

**See:** `docs/CONTAINER_MANAGER.md` for complete agent documentation including analysis criteria.

---

## Manual Release Process

If you prefer manual control or need to customize the release process, follow the steps below.

## Table of Contents

- [Versioning Strategy](#versioning-strategy)
- [Pre-Release Checklist](#pre-release-checklist)
- [Release Process](#release-process)
- [Container Image Tags](#container-image-tags)
- [Hotfix Releases](#hotfix-releases)
- [Pre-Release Versions](#pre-release-versions)
- [Troubleshooting](#troubleshooting)

---

## Versioning Strategy

KATO follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

### Version Bump Rules

- **MAJOR** version when you make incompatible API changes
  - Breaking changes to API endpoints
  - Architecture changes requiring migration
  - Removal of deprecated features
  - Example: `2.0.0` → `3.0.0`

- **MINOR** version when you add functionality in a backward-compatible manner
  - New features and capabilities
  - New API endpoints
  - Performance improvements
  - Example: `2.0.0` → `2.1.0`

- **PATCH** version when you make backward-compatible bug fixes
  - Bug fixes
  - Security patches
  - Documentation updates
  - Example: `2.0.0` → `2.0.1`

### Version Source of Truth

- **Primary**: `pyproject.toml`
- **Synced**: `setup.py`, `kato/__init__.py`
- **Tags**: Git tags (`v2.0.0`)

---

## Pre-Release Checklist

Before creating a release, ensure:

- [ ] All tests pass locally: `./run_tests.sh --no-start --no-stop`
- [ ] All tests pass in CI/CD (if configured)
- [ ] Code is linted: `ruff check kato/`
- [ ] Documentation is updated
- [ ] CHANGELOG.md has all changes documented under `[Unreleased]`
- [ ] No uncommitted changes: `git status`
- [ ] Current branch is `main`: `git branch --show-current`
- [ ] Local branch is up to date: `git pull origin main`

---

## Release Process

### Step 1: Bump Version

Use the `bump-version.sh` script to update version numbers:

```bash
# For a patch release (2.0.0 → 2.0.1)
./bump-version.sh patch "Brief description of changes"

# For a minor release (2.0.0 → 2.1.0)
./bump-version.sh minor "Add new feature"

# For a major release (2.0.0 → 3.0.0)
./bump-version.sh major "Breaking changes"
```

The script will:
1. Extract current version from `pyproject.toml`
2. Increment version based on bump type
3. Update `pyproject.toml`, `setup.py`, and `kato/__init__.py`
4. Optionally create a git commit
5. Optionally create a git tag

**Manual Alternative:**

If you prefer manual updates:

```bash
# Edit version in these files:
vim pyproject.toml    # version = "2.1.0"
vim setup.py          # version="2.1.0"
vim kato/__init__.py  # __version__ = '2.1.0'

# Commit changes
git add pyproject.toml setup.py kato/__init__.py
git commit -m "chore: bump version to 2.1.0"
```

### Step 2: Update CHANGELOG

Move all `[Unreleased]` entries to a new version section:

```bash
vim CHANGELOG.md
```

Change:
```markdown
## [Unreleased]

### Added
- New feature

## [2.0.0] - 2025-10-31
```

To:
```markdown
## [Unreleased]

## [2.1.0] - 2025-11-15

### Added
- New feature

## [2.0.0] - 2025-10-31
```

Commit the changelog:
```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v2.1.0 release"
```

### Step 3: Create Git Tag

Create an annotated tag for the release:

```bash
# Create tag
git tag -a v2.1.0 -m "Release v2.1.0: Brief description"

# Verify tag
git tag -l v2.1.0
git show v2.1.0
```

### Step 4: Push Changes

Push both the commit and tag to GitHub:

```bash
# Push commits
git push origin main

# Push tag
git push origin v2.1.0
```

### Step 5: Build and Push Container Images

Use the `build-and-push.sh` script to build and publish container images:

```bash
# Login to GitHub Container Registry first
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Build and push images
./build-and-push.sh
```

The script will:
1. Extract version from `pyproject.toml`
2. Build Docker image with version metadata
3. Create multiple tags:
   - `ghcr.io/sevakavakians/kato:2.1.0` (specific version)
   - `ghcr.io/sevakavakians/kato:2.1` (minor version)
   - `ghcr.io/sevakavakians/kato:2` (major version)
   - `ghcr.io/sevakavakians/kato:latest` (latest stable)
4. Push all tags to registry

**Options:**

```bash
# Build without pushing (for testing)
./build-and-push.sh --no-push

# Use custom registry
./build-and-push.sh --registry your-registry.io/your-org/kato
```

### Step 6: Create GitHub Release

1. Go to [GitHub Releases](https://github.com/sevakavakians/kato/releases)
2. Click "Draft a new release"
3. Select the tag you just created (e.g., `v2.1.0`)
4. Release title: `KATO v2.1.0`
5. Description: Copy relevant section from CHANGELOG.md
6. Publish release

### Step 7: Verify Release

Verify the release was successful:

```bash
# Check Docker images
docker pull ghcr.io/sevakavakians/kato:2.1.0
docker pull ghcr.io/sevakavakians/kato:latest

# Inspect image metadata
docker inspect ghcr.io/sevakavakians/kato:2.1.0 | grep -A 10 Labels

# Verify version in image
docker run --rm ghcr.io/sevakavakians/kato:2.1.0 python -c "import kato; print(kato.__version__)"
```

---

## Container Image Tags

Each stable release creates **four tags**:

| Tag | Description | Example | Use Case |
|-----|-------------|---------|----------|
| `MAJOR.MINOR.PATCH` | Specific version (immutable) | `2.1.0` | Production pinning |
| `MAJOR.MINOR` | Latest patch for minor version | `2.1` | Auto-receive patches |
| `MAJOR` | Latest minor for major version | `2` | Track major version |
| `latest` | Latest stable release | `latest` | Development/testing |

**Usage Examples:**

```bash
# Pin to specific version (recommended for production)
docker pull ghcr.io/sevakavakians/kato:2.1.0

# Auto-receive patch updates
docker pull ghcr.io/sevakavakians/kato:2.1

# Track major version (may include breaking changes!)
docker pull ghcr.io/sevakavakians/kato:2

# Always use latest (for development only)
docker pull ghcr.io/sevakavakians/kato:latest
```

---

## Hotfix Releases

For urgent bug fixes on a released version:

### Option 1: Patch Release (Recommended)

If `main` branch is stable:

```bash
# Bump to patch version
./bump-version.sh patch "Fix critical bug"

# Update CHANGELOG
vim CHANGELOG.md

# Tag and release
git tag -a v2.1.1 -m "Hotfix: Critical bug fix"
git push origin main
git push origin v2.1.1
./build-and-push.sh
```

### Option 2: Hotfix Branch

If `main` branch has unreleased changes:

```bash
# Create hotfix branch from release tag
git checkout -b hotfix/2.1.1 v2.1.0

# Make fixes
vim kato/some_file.py
git add .
git commit -m "fix: critical bug"

# Bump version
./bump-version.sh patch "Hotfix: Critical bug"

# Tag and push
git tag -a v2.1.1 -m "Hotfix: Critical bug fix"
git push origin hotfix/2.1.1
git push origin v2.1.1

# Build and push
./build-and-push.sh

# Merge back to main
git checkout main
git merge hotfix/2.1.1
git push origin main

# Clean up
git branch -d hotfix/2.1.1
git push origin --delete hotfix/2.1.1
```

---

## Pre-Release Versions

For alpha, beta, or release candidate versions:

### Format

```
MAJOR.MINOR.PATCH-PRERELEASE
```

Examples:
- `2.1.0-alpha.1`
- `2.1.0-beta.1`
- `2.1.0-rc.1`

### Process

```bash
# Manually edit version (no script support for pre-releases yet)
vim pyproject.toml    # version = "2.1.0-beta.1"
vim setup.py          # version="2.1.0-beta.1"
vim kato/__init__.py  # __version__ = '2.1.0-beta.1'

# Commit and tag
git add pyproject.toml setup.py kato/__init__.py
git commit -m "chore: release v2.1.0-beta.1"
git tag -a v2.1.0-beta.1 -m "Pre-release: v2.1.0-beta.1"
git push origin main
git push origin v2.1.0-beta.1

# Build and push (only creates specific version tag, not :latest)
./build-and-push.sh
```

**Note**: Pre-releases do NOT update the `:latest`, `:2.1`, or `:2` tags.

---

## Troubleshooting

### Problem: Build fails with permission error

```bash
# Login to container registry
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

### Problem: Version mismatch across files

```bash
# Use bump-version.sh to ensure consistency
./bump-version.sh patch
```

Or manually sync:
```bash
grep 'version' pyproject.toml setup.py kato/__init__.py
```

### Problem: Tag already exists

```bash
# Delete local tag
git tag -d v2.1.0

# Delete remote tag
git push origin --delete v2.1.0

# Recreate tag
git tag -a v2.1.0 -m "Release v2.1.0"
git push origin v2.1.0
```

### Problem: Image not showing up in registry

Check:
1. Correct authentication: `docker login ghcr.io`
2. Package visibility settings in GitHub
3. Push command output for errors
4. Registry URL is correct: `ghcr.io/sevakavakians/kato`

### Problem: Old version showing in container

```bash
# Clear Docker cache
docker system prune -a

# Rebuild with no cache
docker build --no-cache -t test-image .

# Verify version
docker run --rm test-image python -c "import kato; print(kato.__version__)"
```

---

## Quick Reference

```bash
# Complete release flow
./bump-version.sh minor "Add new feature"     # Step 1: Bump version
vim CHANGELOG.md                               # Step 2: Update changelog
git add CHANGELOG.md && git commit -m "docs: update CHANGELOG"
git tag -a v2.1.0 -m "Release v2.1.0"         # Step 3: Create tag
git push origin main && git push origin v2.1.0 # Step 4: Push
./build-and-push.sh                            # Step 5: Build & push images
```

---

## Additional Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Docker Multi-arch Builds](https://docs.docker.com/build/building/multi-platform/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
