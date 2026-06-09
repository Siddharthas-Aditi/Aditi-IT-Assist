# Docker Standards

## Image Guidelines
- Use slim/alpine base images
- Multi-stage builds for frontend
- Pin major versions (e.g., `python:3.12-slim`, `node:20-alpine`)
- Include health checks
- Don't run as root in production

## Docker Compose
- Use named volumes for data persistence
- Define health checks with `service_healthy` conditions
- Use environment variables (not hardcoded values)
- Order services by dependency

## Local Development
```bash
docker compose up --build          # Full stack
docker compose up postgres redis -d  # Infra only
docker compose logs -f backend     # Tail backend logs
docker compose down -v             # Clean shutdown
```
