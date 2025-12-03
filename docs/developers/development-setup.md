# Development Setup Guide

Complete guide to setting up a KATO development environment.

## Prerequisites

### Required Software

- **Python 3.10+**: Main development language
- **Docker Desktop**: For running services
- **Git**: Version control
- **Make**: Build automation (optional)

### Recommended Tools

- **IDE**: PyCharm, VS Code, or similar
- **DBeaver**: Database GUI for ClickHouse/Redis (optional)
- **Postman/Insomnia**: API testing (optional)

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-org/kato.git
cd kato
```

### 2. Python Environment

#### Using venv (Recommended)

```bash
# Create virtual environment
python3.10 -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
.\venv\Scripts\activate   # Windows

# Upgrade pip
pip install --upgrade pip
```

#### Using conda (Alternative)

```bash
conda create -n kato python=3.10
conda activate kato
```

### 3. Install Dependencies

#### Development Dependencies

```bash
# Install all dependencies including dev tools
pip install -r requirements.txt
pip install -r requirements-dev.txt  # If separate file exists

# Or install in editable mode
pip install -e .
```

#### Lock File

KATO uses `requirements.lock` for reproducible builds:

```bash
# Install from lock file (production-like)
pip install -r requirements.lock

# Update lock file after changing requirements.txt
pip-compile --output-file=requirements.lock requirements.txt
```

### 4. Environment Configuration

Create `.env` file in project root:

```bash
# Copy template
cp .env.example .env

# Or create from scratch
cat > .env << EOF
# Service Configuration
LOG_LEVEL=DEBUG
LOG_FORMAT=human
ENVIRONMENT=development

# Database Configuration
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379/0

# Learning Configuration
MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.1
STM_MODE=CLEAR

# Session Configuration
SESSION_TTL=3600
SESSION_AUTO_EXTEND=true

# Development Settings
DEBUG=true
DOCS_ENABLED=true
CORS_ENABLED=true
CORS_ORIGINS=*
EOF
```

### 5. Start Services

```bash
# Start all services (ClickHouse, Qdrant, Redis, KATO)
./start.sh

# Or manually with docker compose
docker compose up -d

# Verify services are running
docker compose ps
```

### 6. Verify Installation

```bash
# Check KATO health
curl http://localhost:8000/health

# Check API docs
open http://localhost:8000/docs  # macOS
xdg-open http://localhost:8000/docs  # Linux

# Run tests
./run_tests.sh --no-start --no-stop
```

## Project Structure

```
kato/
├── kato/                   # Main package
│   ├── api/               # FastAPI endpoints
│   ├── config/            # Configuration
│   ├── workers/           # Core processors
│   ├── storage/           # Database adapters
│   ├── searches/          # Pattern matching
│   ├── sessions/          # Session management
│   └── informatics/       # Information theory
├── tests/                 # Test suite
│   ├── fixtures/          # Test fixtures
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── api/               # API tests
├── docs/                  # Documentation
├── scripts/               # Utility scripts
├── docker compose.yml     # Docker services
├── Dockerfile             # KATO container
├── requirements.txt       # Python dependencies
├── requirements.lock      # Locked dependencies
└── start.sh              # Service startup script
```

## Development Workflow

### Running KATO Locally

#### Option 1: Docker (Recommended)

```bash
# Start all services
./start.sh

# View logs
docker compose logs -f kato

# Restart after code changes
docker compose restart kato

# Rebuild after dependency changes
docker compose build --no-cache kato
docker compose up -d
```

#### Option 2: Local Python (Advanced)

```bash
# Start dependencies only
docker compose up -d kato-clickhouse qdrant-kb redis-kb

# Run KATO locally
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_DB=kato
export QDRANT_HOST=localhost
export REDIS_URL=redis://localhost:6379/0

python -m uvicorn kato.api.main:app --reload --port 8000
```

**Benefits**:
- Faster iteration (no container rebuild)
- Better debugger integration
- Direct code access

**Drawbacks**:
- Must manage environment variables
- May have platform-specific issues

### Making Code Changes

1. **Create feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes**
   - Edit code in `kato/` directory
   - Follow [Code Style Guide](code-style.md)

3. **Test changes**
   ```bash
   # Restart KATO to pick up changes
   docker compose restart kato

   # Run affected tests
   python -m pytest tests/unit/test_my_module.py -v
   ```

4. **Commit changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

See [Git Workflow](git-workflow.md) for branching strategy.

## Testing

### Running Tests

```bash
# All tests
./run_tests.sh --no-start --no-stop

# Specific suite
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v
python -m pytest tests/api/ -v

# Specific test file
python -m pytest tests/unit/test_observations.py -v

# Specific test
python -m pytest tests/unit/test_observations.py::test_observe_single_string -v

# With coverage
python -m pytest tests/ --cov=kato --cov-report=html
open htmlcov/index.html
```

### Test Configuration

Tests connect to Docker services but run in local Python:

```python
# tests/fixtures/kato_fixtures.py
@pytest.fixture
def kato_client():
    """Create KATO client for testing."""
    return KATOClient("http://localhost:8000")
```

**Key Points**:
- Each test gets unique `processor_id` for isolation
- Tests expect services running on standard ports
- No container rebuild needed for test changes

See [Testing Guide](testing.md) for comprehensive coverage.

## IDE Setup

### Visual Studio Code

#### Recommended Extensions

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.black-formatter",
    "charliermarsh.ruff",
    "tamasfe.even-better-toml",
    "redhat.vscode-yaml"
  ]
}
```

#### Settings

Create `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

#### Launch Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "KATO API",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "kato.api.main:app",
        "--reload",
        "--port", "8000"
      ],
      "env": {
        "CLICKHOUSE_HOST": "localhost",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_DB": "kato",
        "QDRANT_HOST": "localhost",
        "REDIS_URL": "redis://localhost:6379/0",
        "LOG_LEVEL": "DEBUG"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "Pytest Current File",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v"
      ]
    }
  ]
}
```

### PyCharm

#### Project Setup

1. **File > Open** → Select kato directory
2. **Preferences > Project > Python Interpreter** → Select venv
3. **Enable pytest**: Preferences > Tools > Python Integrated Tools > Testing → pytest

#### Run Configurations

**KATO API**:
- Script path: `<venv>/bin/uvicorn`
- Parameters: `kato.api.main:app --reload --port 8000`
- Environment variables: (same as VS Code)

**Pytest**:
- Target: tests/
- Options: `-v`

## Code Quality Tools

### Linting

```bash
# Ruff (fast linter)
ruff check kato/
ruff check --fix kato/  # Auto-fix

# Check specific file
ruff check kato/api/endpoints/sessions.py
```

### Formatting

```bash
# Black (code formatter)
black kato/
black tests/

# Check without modifying
black --check kato/
```

### Type Checking

```bash
# MyPy (static type checker)
mypy kato/ --ignore-missing-imports

# Specific module
mypy kato/workers/kato_processor.py
```

### Pre-commit Hooks (Optional)

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Debugging

### Docker Logs

```bash
# Follow KATO logs
docker compose logs -f kato

# All logs
docker compose logs

# Last 100 lines
docker compose logs --tail 100 kato
```

### Python Debugger

#### VS Code

1. Set breakpoints in code
2. Press F5 or Run > Start Debugging
3. Use Debug Console for inspection

#### PyCharm

1. Set breakpoints in code
2. Right-click > Debug 'pytest' or Debug 'KATO API'
3. Use Debugger tab for inspection

#### Command Line (pdb)

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Run script
python -m uvicorn kato.api.main:app --reload

# When breakpoint hits:
# (Pdb) print(variable_name)
# (Pdb) next  # Next line
# (Pdb) continue  # Continue execution
```

See [Debugging Guide](debugging.md) for advanced techniques.

## Database Access

### ClickHouse

```bash
# Connect with CLI
docker exec -it kato-clickhouse clickhouse-client

# Use specific database
USE kato

# List tables
SHOW TABLES

# Query patterns
SELECT * FROM patterns LIMIT 10
SELECT count() FROM patterns
```

### DBeaver (GUI)

```
Host: localhost
Port: 8123
Database: kato
```

Browse tables in the `kato` database

### Qdrant

```bash
# Web UI
open http://localhost:6333/dashboard

# API
curl http://localhost:6333/collections
```

### Redis

```bash
# Connect with CLI
docker exec -it redis-kb-$USER-1 redis-cli

# List all keys
KEYS *

# Get session data
GET session:session-abc123

# Get all session keys
KEYS session:*
```

## Updating Dependencies

### Adding New Dependency

```bash
# 1. Add to requirements.txt
echo "new-package==1.0.0" >> requirements.txt

# 2. Regenerate lock file
pip-compile --output-file=requirements.lock requirements.txt

# 3. Rebuild Docker image
docker compose build --no-cache kato

# 4. Restart services
docker compose up -d
```

### Upgrading Dependencies

```bash
# Upgrade specific package
pip install --upgrade package-name
pip freeze | grep package-name  # Get new version

# Update requirements.txt with new version

# Regenerate lock file
pip-compile --output-file=requirements.lock requirements.txt

# Test changes
./run_tests.sh --no-start --no-stop
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
docker version

# Check port conflicts
lsof -i :8000
lsof -i :8123
lsof -i :6333

# Clean and rebuild
docker compose down
docker system prune -f
./start.sh
```

### Tests Failing

```bash
# Ensure services are running
docker compose ps  # All should be "Up"

# Check service health
curl http://localhost:8000/health
docker exec kato-clickhouse clickhouse-client --query "SELECT version()"

# Clear test data
docker exec kato-clickhouse clickhouse-client --query "SHOW DATABASES" | grep test
# Drop test databases if needed

# Rerun with verbose output
python -m pytest tests/unit/test_observations.py -vv
```

### Import Errors

```bash
# Reinstall in editable mode
pip install -e .

# Check Python path
python -c "import sys; print(sys.path)"

# Verify KATO is importable
python -c "import kato; print(kato.__file__)"
```

## Next Steps

1. Review [Code Organization](code-organization.md)
2. Read [Architecture Overview](architecture.md)
3. Understand [Data Flow](data-flow.md)
4. Learn [Design Patterns](design-patterns.md)
5. See [Contributing Guide](contributing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
