# KATO Dependency Management

## Overview

Strategy for managing Python dependencies, version updates, compatibility testing, and security maintenance.

## Table of Contents
1. [Dependency Strategy](#dependency-strategy)
2. [Update Process](#update-process)
3. [Version Pinning](#version-pinning)
4. [Compatibility Testing](#compatibility-testing)

## Dependency Strategy

### Dependency Files

```
requirements.txt          # Abstract dependencies (ranges)
requirements.lock         # Concrete dependencies (pinned)
pyproject.toml           # Poetry/build configuration
```

**requirements.txt** (abstract):
```
httpx>=0.25.0,<1.0.0
pydantic>=2.0.0,<3.0.0
redis>=5.0.0,<6.0.0
```

**requirements.lock** (concrete):
```
httpx==0.25.2
pydantic==2.4.2
redis==5.0.1
certifi==2023.11.17  # transitive dependency
```

### Dependency Categories

**Production Dependencies:**
- FastAPI ecosystem (fastapi, uvicorn, httpx)
- Storage (clickhouse-connect, redis, qdrant-client)
- Configuration (pydantic-settings)
- Utilities (python-multipart, python-jose)

**Development Dependencies:**
- Testing (pytest, pytest-cov, pytest-asyncio)
- Code quality (ruff, mypy, bandit)
- Documentation (sphinx, mkdocs)

## Update Process

### Regular Updates (Monthly)

```bash
# 1. Check for updates
pip list --outdated

# 2. Update requirements.txt with new ranges
vim requirements.txt

# 3. Regenerate lock file
pip-compile --upgrade --output-file=requirements.lock requirements.txt

# 4. Install updated dependencies
pip install -r requirements.lock

# 5. Run full test suite
pytest tests/

# 6. Check for security vulnerabilities
pip-audit --requirement requirements.lock

# 7. Update Docker image
docker-compose build --no-cache kato

# 8. Test Docker image
docker-compose up -d
curl http://localhost:8000/health

# 9. Commit changes
git add requirements.txt requirements.lock
git commit -m "deps: update dependencies (monthly maintenance)"
```

### Security Updates (As Needed)

```bash
# 1. Identify vulnerable dependency
pip-audit --requirement requirements.lock

# 2. Update specific dependency
pip-compile --upgrade-package httpx --output-file=requirements.lock requirements.txt

# 3. Test immediately
pytest tests/

# 4. Deploy as patch release
./container-manager.sh patch "Security update: httpx 0.25.2"
```

### Major Version Updates

```bash
# Example: FastAPI 0.x → 1.0

# 1. Create feature branch
git checkout -b deps/fastapi-1.0

# 2. Update requirements.txt
# Before: fastapi>=0.100.0,<1.0.0
# After:  fastapi>=1.0.0,<2.0.0

# 3. Regenerate lock
pip-compile --output-file=requirements.lock requirements.txt

# 4. Install
pip install -r requirements.lock

# 5. Fix breaking changes
# (Review FastAPI 1.0 migration guide)

# 6. Run tests
pytest tests/

# 7. Update documentation
vim docs/reference/api-compatibility.md

# 8. Create PR
git push origin deps/fastapi-1.0
```

## Version Pinning

### Pinning Strategy

```
# requirements.txt (abstract)
# Use compatible release operator (~=) for most deps
httpx~=0.25.0       # Allow 0.25.x, not 0.26.0
pydantic~=2.4.0     # Allow 2.4.x, not 2.5.0

# Pin exact versions for known issues
some-lib==1.2.3     # Specific version required

# Allow wider range for stable libraries
certifi>=2023.0.0   # CA certificates, update freely
```

### Lock File

```bash
# Generate lock file with hashes for security
pip-compile --generate-hashes --output-file=requirements.lock requirements.txt

# Result includes SHA256 hashes
httpx==0.25.2 \
    --hash=sha256:abc123... \
    --hash=sha256:def456...
```

## Compatibility Testing

### Test Matrix

```yaml
# .github/workflows/compatibility.yml
strategy:
  matrix:
    python-version: ['3.10', '3.11', '3.12']
    dependency-set:
      - name: minimum
        requirements: requirements.min.txt
      - name: latest
        requirements: requirements.lock
```

### Dependency Versions

```
# requirements.min.txt (minimum supported)
httpx==0.25.0
pydantic==2.0.0
redis==5.0.0

# requirements.lock (current tested)
httpx==0.25.2
pydantic==2.4.2
redis==5.0.1

# requirements.max.txt (maximum allowed)
httpx==0.99.0
pydantic==2.99.0
redis==5.99.0
```

## Best Practices

1. **Use lock files** - Reproducible builds
2. **Update regularly** - Monthly scheduled updates
3. **Test thoroughly** - Full test suite on updates
4. **Security first** - Patch vulnerabilities immediately
5. **Document changes** - Note breaking changes
6. **Automate** - CI/CD checks for vulnerabilities

## Related Documentation

- [Security Guidelines](security.md)
- [Vulnerability Management](vulnerability-management.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
