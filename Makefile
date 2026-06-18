# ==================================================
# Aditi IT Assist — Makefile
# ==================================================
# Unified commands for development, testing, and deployment
#
# Quick start:
#   make bootstrap   → First-time setup
#   make dev         → Full stack (Docker, hot-reload)
#   make dev-local   → Backend + frontend without Docker
#   make test        → Run all tests

.PHONY: help install dev test lint format docker-up docker-down clean seed

SHELL := /bin/zsh
UV := uv

# ─── Default ────────────────────────────────────

help: ## Show this help
	@echo "\033[1mAditi IT Assist\033[0m — available targets:\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Installation ───────────────────────────────

install: install-backend install-frontend install-hooks ## Install all dependencies

install-backend: ## Install backend dependencies
	cd backend && $(UV) sync

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

install-hooks: ## Enable git hooks (pre-push checks) for this clone
	git config core.hooksPath .githooks
	@echo "✅ git hooks enabled (core.hooksPath=.githooks) — pre-push checks active"

# ─── Development ────────────────────────────────

dev: ## Start full stack via Docker Compose (hot-reload)
	docker compose up --build

dev-infra: ## Start only Postgres + Redis (for local backend/frontend)
	docker compose up postgres redis -d
	@echo "\n✅ Infrastructure ready — Postgres:5432 Redis:6379"

dev-local: dev-infra ## Run backend + frontend locally (requires dev-infra)
	@echo "Starting backend and frontend..."
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Start backend in dev mode (hot-reload)
	cd backend && $(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Start frontend in dev mode (Vite HMR)
	cd frontend && npm run dev

# ─── Database ───────────────────────────────────

db-migrate: ## Run database migrations
	cd backend && $(UV) run alembic upgrade head

db-revision: ## Create new migration (usage: make db-revision MSG="description")
	cd backend && $(UV) run alembic revision --autogenerate -m "$(MSG)"

db-downgrade: ## Rollback last migration
	cd backend && $(UV) run alembic downgrade -1

db-reset: ## Drop and recreate database (destructive!)
	docker compose exec postgres psql -U aditi -c "DROP DATABASE IF EXISTS aditi_assist;"
	docker compose exec postgres psql -U aditi -c "CREATE DATABASE aditi_assist;"
	@echo "✅ Database reset. Run: make db-migrate"

seed: ## Seed knowledge base into database
	cd backend && $(UV) run python -m scripts.seed_data

# ─── Testing ────────────────────────────────────

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && $(UV) run pytest -v

test-frontend: ## Run frontend tests
	cd frontend && npm run test

test-e2e: ## Run Playwright E2E tests (needs backend running + seeded)
	cd frontend && npm run test:e2e

test-e2e-ui: ## Open the Playwright UI runner
	cd frontend && npm run test:e2e:ui

test-coverage: ## Run backend tests with coverage
	cd backend && $(UV) run pytest --cov=app --cov-report=term --cov-report=html

test-watch: ## Run backend tests in watch mode
	cd backend && $(UV) run pytest --watch

# ─── Code Quality ───────────────────────────────

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

# ─── Docker ─────────────────────────────────────

docker-up: ## Start all services (detached, production-like)
	docker compose --profile prod up --build -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail all container logs
	docker compose logs -f --tail=50

docker-ps: ## Show running containers and health
	docker compose ps

docker-shell-backend: ## Open shell in backend container
	docker compose exec backend bash

docker-shell-db: ## Open psql in postgres container
	docker compose exec postgres psql -U aditi -d aditi_assist

docker-clean: ## Remove all containers, volumes, images
	docker compose down -v --remove-orphans --rmi local

# ─── Utilities ──────────────────────────────────

clean: ## Clean build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist backend/.coverage htmlcov

bootstrap: ## First-time project setup (installs everything)
	chmod +x scripts/*.sh
	./scripts/bootstrap.sh

smoke-test: ## Verify running services respond correctly
	./scripts/smoke_test.sh

logs: docker-logs ## Alias for docker-logs
