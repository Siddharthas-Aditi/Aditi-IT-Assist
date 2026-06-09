# ==================================================
# Aditi IT Assist - Makefile
# ==================================================
# Unified commands for development, testing, and deployment

.PHONY: help install dev test lint format docker-up docker-down clean seed

SHELL := /bin/zsh
PYTHON := python3
UV := uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==================================================
# Installation
# ==================================================

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install backend dependencies
	cd backend && $(UV) sync

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

# ==================================================
# Development
# ==================================================

dev: ## Start full development stack via docker-compose
	docker compose up --build

dev-backend: ## Start backend in development mode
	cd backend && $(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Start frontend in development mode
	cd frontend && npm run dev

# ==================================================
# Database
# ==================================================

db-migrate: ## Run database migrations
	cd backend && $(UV) run alembic upgrade head

db-revision: ## Create new migration (usage: make db-revision MSG="description")
	cd backend && $(UV) run alembic revision --autogenerate -m "$(MSG)"

db-downgrade: ## Rollback last migration
	cd backend && $(UV) run alembic downgrade -1

seed: ## Seed database with sample data
	cd backend && $(UV) run python -m scripts.seed_data

# ==================================================
# Testing
# ==================================================

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && $(UV) run pytest

test-frontend: ## Run frontend tests
	cd frontend && npm run test

test-coverage: ## Run tests with coverage report
	cd backend && $(UV) run pytest --cov --cov-report=html

# ==================================================
# Code Quality
# ==================================================

lint: lint-backend lint-frontend ## Lint all code

lint-backend: ## Lint backend code
	cd backend && $(UV) run ruff check .

lint-frontend: ## Lint frontend code
	cd frontend && npm run lint

format: format-backend format-frontend ## Format all code

format-backend: ## Format backend code
	cd backend && $(UV) run ruff format .

format-frontend: ## Format frontend code
	cd frontend && npm run format

typecheck: ## Run type checking
	cd backend && $(UV) run mypy app/
	cd frontend && npm run typecheck

# ==================================================
# Docker
# ==================================================

docker-up: ## Start all services with Docker Compose
	docker compose up --build -d

docker-down: ## Stop all Docker services
	docker compose down

docker-logs: ## Tail Docker logs
	docker compose logs -f

docker-clean: ## Remove all containers and volumes
	docker compose down -v --remove-orphans

# ==================================================
# Utilities
# ==================================================

clean: ## Clean build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist backend/.coverage htmlcov output/*

bootstrap: ## First-time project setup
	chmod +x scripts/*.sh
	./scripts/bootstrap.sh

smoke-test: ## Run smoke tests against running services
	./scripts/smoke_test.sh
