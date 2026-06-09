# Docker Agent Prompt

Manage containerization for Aditi IT Assist:

## Services
- `postgres`: pgvector/pgvector:pg16
- `redis`: redis:7-alpine
- `backend`: Python 3.12 + FastAPI
- `frontend`: Node 20 build → nginx serve

## Commands
- `docker compose up --build` — full stack
- `docker compose up postgres redis -d` — infra only
- `docker compose logs -f backend` — tail logs

## Requirements
- Health checks on all services
- Named volumes for persistence
- Environment variable wiring
- Service dependency ordering
