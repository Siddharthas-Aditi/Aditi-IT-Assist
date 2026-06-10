# Skill: Docker Patterns

> Container best practices for Aditi IT Assist.

---

## Multi-Stage Builds

Both backend and frontend use multi-stage Dockerfiles:

```dockerfile
# Stage 1: Base (shared deps)
FROM python:3.12-slim AS base
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync

# Stage 2: Development (hot-reload)
FROM base AS development
COPY . .
CMD ["uvicorn", "app.main:app", "--reload"]

# Stage 3: Production (optimized)
FROM base AS production
RUN uv sync --no-dev
COPY . .
USER appuser
CMD ["uvicorn", "app.main:app", "--workers", "2"]
```

---

## Docker Compose Patterns

```yaml
services:
  backend:
    build:
      target: development        # Use dev stage
    volumes:
      - ./backend/app:/app/app   # Hot-reload mount
    depends_on:
      postgres:
        condition: service_healthy  # Wait for healthy deps
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; ..."]
      interval: 5s
```

---

## Health Checks

Every service must have a health check:

| Service | Check Method |
|---------|-------------|
| Backend | HTTP GET `/api/v1/health` |
| Frontend | HTTP GET `/` |
| PostgreSQL | `pg_isready` |
| Redis | `redis-cli ping` |

---

## Volume Strategy

| Type | Mount | Purpose |
|------|-------|---------|
| Source code | bind mount | Hot-reload in dev |
| Database data | named volume | Persist across restarts |
| Node modules | named volume | Avoid host/container conflicts |
| Build cache | named volume | Speed up rebuilds |

---

## Environment Variables

- Use `.env` file (gitignored) for local dev
- Use `env_file:` in docker-compose for container vars
- Override per-environment in compose service `environment:` block
- Never bake secrets into images
