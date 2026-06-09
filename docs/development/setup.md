# Development Setup — Aditi IT Assist

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- uv (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Git

## Quick Start

```bash
# Clone and enter project
cd aditi-it-assist

# Run bootstrap (installs deps, creates .env, sets up pre-commit)
make bootstrap

# Start all services with Docker
make dev

# Or run individually:
make dev-backend   # FastAPI on :8000
make dev-frontend  # Vite on :5173
```

## Manual Setup

### Backend
```bash
cd backend
uv sync                          # Install dependencies
cp .env.example .env             # Configure environment
uv run alembic upgrade head      # Run migrations
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install                      # Install dependencies
cp .env.example .env             # Configure environment
npm run dev                      # Start dev server on :5173
```

### Database
```bash
# Start PostgreSQL and Redis via Docker
docker compose up postgres redis -d

# Run migrations
cd backend && uv run alembic upgrade head

# Seed with sample data
make seed
```

## Environment Variables

Copy `.env.example` to `.env` at the project root and configure:
- `LLM_API_KEY` — Your OpenAI/Azure API key
- `POSTGRES_*` — Database connection (defaults work with Docker)
- `REDIS_*` — Redis connection (defaults work with Docker)

## IDE Setup

VS Code is the recommended editor. Open the workspace and install recommended extensions:
- Python (ms-python)
- Pylance
- Ruff
- ESLint
- Tailwind CSS IntelliSense
- Docker

## Running Tests

```bash
make test              # All tests
make test-backend      # Backend only
make test-frontend     # Frontend only
make test-coverage     # With coverage report
```

## Code Quality

```bash
make lint              # Run all linters
make format            # Auto-format code
make typecheck         # Type checking
```
