# PROJECT-HYGIENE.md

## Keeping the KATO Project Clean and Efficient

This document outlines best practices for maintaining a clean, efficient codebase that avoids memory issues when being read by AI assistants or analyzed by tools.

### Target Size: < 15MB

The KATO project should remain under 15MB to ensure it can be fully analyzed without memory constraints. The actual source code is only ~10MB - everything else is generated artifacts.

## Regular Cleanup Tasks

### 1. Virtual Environments - DELETE ON SIGHT
**Frequency**: Whenever spotted  
**Locations to check**:
- `kato_venv/`
- `tests/venv/`
- `tests/tests/venv/`
- Any `**/venv/` directories

**Action**:
```bash
rm -rf kato_venv tests/venv tests/tests/venv
```

**Why**: All KATO code runs in Docker containers. Virtual environments are unnecessary and add 100MB+ of bloat.

### 2. Coverage Reports
**Frequency**: After each test coverage run  
**Location**: `htmlcov/`

**Action**:
```bash
rm -rf htmlcov/
```

**Why**: Coverage reports are regeneratable artifacts. Run tests with `--cov` flag to recreate when needed.

### 3. Log Rotation
**Frequency**: Weekly or when logs exceed 1MB  
**Locations**: 
- `logs/kato-manager.log`
- `logs/test-results.log`

**Action** (keeps last 1000 lines):
```bash
tail -1000 logs/kato-manager.log > logs/kato-manager.log.tmp && mv logs/kato-manager.log.tmp logs/kato-manager.log
tail -1000 logs/test-results.log > logs/test-results.log.tmp && mv logs/test-results.log.tmp logs/test-results.log
```

**Why**: Logs accumulate quickly during development. Old entries are rarely needed.

### 4. Python Cache Files
**Frequency**: Before commits  
**Locations**: `__pycache__/`, `*.pyc`, `*.pyo`

**Action**:
```bash
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -o -name "*.pyo" -exec rm -f {} + 2>/dev/null
```

**Why**: Python bytecode is regenerated automatically. No need to store it.

## Quick Health Check

Run this command to check project size and identify bloat:
```bash
# Check total size
du -sh .

# Find directories over 1MB
du -h . | grep -E "^[0-9]+M" | sort -rh

# Check for common bloat
echo "Checking for virtual environments..."
find . -type d -name "venv" -o -name "*_venv" 2>/dev/null

echo "Checking for coverage reports..."
ls -la htmlcov/ 2>/dev/null || echo "No coverage reports found (good!)"

echo "Checking log sizes..."
ls -lh logs/*.log 2>/dev/null
```

## One-Line Cleanup

For quick cleanup before AI analysis or commits:
```bash
rm -rf kato_venv tests/venv tests/tests/venv htmlcov/ && tail -1000 logs/kato-manager.log > logs/kato-manager.log.tmp && mv logs/kato-manager.log.tmp logs/kato-manager.log && tail -1000 logs/test-results.log > logs/test-results.log.tmp && mv logs/test-results.log.tmp logs/test-results.log
```

## Prevention via .gitignore

Ensure these patterns are in `.gitignore`:
```gitignore
# Virtual environments
kato_venv/
tests/venv/
tests/tests/venv/
**/venv/

# Coverage reports  
htmlcov/
.coverage

# Large log files
logs/*.log
```

## Red Flags - Items That Should Never Exist

1. **Any directory named `venv`** - We use Docker, not local Python
2. **`node_modules/`** - This is a Python project
3. **`.tox/`, `.nox/`** - Testing happens in Docker containers
4. **`*.egg-info/` in root** - Should only exist temporarily during pip install
5. **Multiple `htmlcov/` directories** - Only one should exist temporarily
6. **Log files over 5MB** - Rotate them immediately

## Monitoring Script

Save this as `check-hygiene.sh`:
```bash
#!/bin/bash
echo "KATO Project Hygiene Check"
echo "=========================="

# Check total size
TOTAL_SIZE=$(du -sh . | cut -f1)
echo "Total project size: $TOTAL_SIZE"

# Check for venvs
VENV_COUNT=$(find . -type d -name "*venv*" 2>/dev/null | wc -l)
if [ $VENV_COUNT -gt 0 ]; then
    echo "⚠️  WARNING: Found $VENV_COUNT virtual environment(s)"
    find . -type d -name "*venv*" 2>/dev/null
fi

# Check for coverage
if [ -d "htmlcov" ]; then
    COVERAGE_SIZE=$(du -sh htmlcov | cut -f1)
    echo "⚠️  WARNING: Coverage reports present ($COVERAGE_SIZE)"
fi

# Check log sizes
for log in logs/*.log; do
    if [ -f "$log" ]; then
        SIZE=$(ls -lh "$log" | awk '{print $5}')
        LINES=$(wc -l < "$log")
        echo "Log: $(basename $log) - Size: $SIZE, Lines: $LINES"
    fi
done

echo ""
if [ $VENV_COUNT -eq 0 ] && [ ! -d "htmlcov" ]; then
    echo "✅ Project is clean!"
else
    echo "❌ Project needs cleanup - run the one-line cleanup command"
fi
```

## When to Run Cleanup

- **Before using AI assistants** (Claude, GitHub Copilot, etc.)
- **Before running comprehensive project analysis**
- **Weekly during active development**
- **Before major commits or pull requests**
- **When project size exceeds 15MB**

## Remember

**Everything runs in Docker** - If you find yourself creating virtual environments or installing packages locally, stop and use the Docker containers instead:
- Production: `./kato-manager.sh`
- Testing: `./test-harness.sh`