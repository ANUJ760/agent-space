.PHONY: help setup test lint format check clean dev-docker-up dev-docker-down db-migrate db-makemigrations db-downgrade db-history db-current

# Default target
help:
	@echo "======================================================================"
	@echo "Agent Space — Modular Engineering & Build Commands"
	@echo "======================================================================"
	@echo "  make setup            Install Python and Node workspace dependencies"
	@echo "  make test             Run test suite using pytest"
	@echo "  make lint             Run code linters (ruff, mypy)"
	@echo "  make format           Auto-format codebases (ruff, prettier)"
	@echo "  make check            Run all verifications (lint + test)"
	@echo "  make clean            Clean ephemeral build caches and test outputs"
	@echo "  make db-migrate       Apply all pending database migrations"
	@echo "  make db-makemigrations m=\"...\" Generate a new migration revision"
	@echo "  make db-downgrade     Roll back the last applied migration"
	@echo "  make db-history       Show database migration history"
	@echo "  make db-current       Show current database revision"
	@echo "  make dev-docker-up    Start backing infrastructure (Postgres, Redis, etc.)"
	@echo "  make dev-docker-down  Stop backing infrastructure"
	@echo "======================================================================"

setup:
	@echo "Setting up Python environment..."
	python3 -m pip install -e ".[dev]"
	@echo "Setting up Node workspace..."
	npm install

test:
	@echo "Running tests..."
	python3 -m pytest tests -v

lint:
	@echo "Running Ruff linter..."
	python3 -m ruff check .
	@echo "Running Mypy type checker..."
	python3 -m mypy apps agents packages tests --ignore-missing-imports || true

format:
	@echo "Formatting Python files..."
	python3 -m ruff format .
	@echo "Formatting Node files..."
	npx prettier --write "**/*.{json,md,yaml,yml}" --ignore-path .gitignore || true

check: lint test

clean:
	@echo "Cleaning temporary files and caches..."
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	rm -rf dist build *.egg-info

dev-docker-up:
	docker compose -f infrastructure/docker-compose.yml up -d

dev-docker-down:
	docker compose -f infrastructure/docker-compose.yml down

db-migrate:
	python3 -m alembic upgrade head

db-makemigrations:
	python3 -m alembic revision --autogenerate -m "$(m)"

db-downgrade:
	python3 -m alembic downgrade -1

db-history:
	python3 -m alembic history --verbose

db-current:
	python3 -m alembic current
