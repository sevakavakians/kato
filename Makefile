.PHONY: help install install-dev run lint format security dead-code quality test test-cov clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: ## Install development dependencies
	pip install -r requirements-dev.txt
	pre-commit install

# Local (non-Docker) run. Override on the command line, e.g.
#   make run PORT=8080
#   make run RELOAD=          (disable auto-reload)
# Configuration comes from .env (see .env.example); exported shell variables win.
# Backing services must be reachable at the configured hosts -- the defaults are
# localhost, which matches the ports ./start.sh publishes.
HOST ?= 0.0.0.0
PORT ?= 8000
RELOAD ?= --reload

run: ## Run KATO locally without Docker (override HOST/PORT/RELOAD)
	uvicorn kato.services.kato_fastapi:app --host $(HOST) --port $(PORT) $(RELOAD)

lint: ## Run linter (ruff)
	ruff check kato/ tests/

format: ## Format code with ruff
	ruff format kato/ tests/
	ruff check --fix kato/ tests/

security: ## Run security checks (bandit)
	bandit -r kato/ -c pyproject.toml

dead-code: ## Find unused code (vulture)
	vulture kato/ --min-confidence 80

quality: lint security ## Run all code quality checks
	@echo "✅ All quality checks passed!"

test: ## Run tests
	pytest tests/tests/unit/ -v

test-integration: ## Run integration tests
	pytest tests/tests/integration/ -v

test-api: ## Run API tests
	pytest tests/tests/api/ -v

test-all: ## Run all tests
	pytest tests/tests/ -v

test-cov: ## Run tests with coverage report
	pytest tests/tests/ --cov=kato --cov-report=term-missing --cov-report=html

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

docker-build: ## Build Docker image (no cache)
	docker compose build --no-cache

docker-up: ## Start Docker services
	./start.sh

docker-down: ## Stop Docker services
	docker compose down

docker-restart: ## Restart Docker services
	docker compose restart

docker-logs: ## View Docker logs
	docker compose logs -f kato
