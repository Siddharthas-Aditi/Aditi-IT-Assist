# Production Deployment Guide

> Companion docs: `rollback-plan.md`, `monitoring-guide.md`,
> `staging-validation.md`, `docs/development/release-checklist.md`.

## Release model

1. CI (lint + typecheck + tests + docker build) must be green on `main`.
2. Tag a release: `git tag v1.2.3 && git push origin v1.2.3`.
3. `.github/workflows/release.yml` re-runs the full CI gate, then publishes
   `ghcr.io/<org>/<repo>-backend:{1.2.3,sha}` and `…-frontend:{1.2.3,sha}`
   and drafts release notes. Publishing ≠ deploying.
4. Deploy to **staging**, run `staging-validation.md`, then deploy to
   production.

## Boot-time safety

The backend **refuses to start** in production (`APP_ENV=production`) if any
of these hold (`Settings.validate_production`):
- `SECRET_KEY` is a placeholder or < 32 chars
- `DEBUG=true`
- `POSTGRES_PASSWORD` is the dev default or empty
- `REDIS_PASSWORD` is empty
- `CORS_ORIGINS` still contains localhost
- `FEATURE_MCP_TOOLS=true` while `MCP_USE_MOCK=true`
- `REMOTE_SUPPORT_USE_MOCK=false` without `REMOTE_HELP_*` credentials

A refused boot logs each `production_config_violation` before exiting.

## First deployment

```bash
# 1. Server prep: Docker Engine 24+, compose v2, 4GB+ RAM.
git clone <repo> && cd aditi-assist
cp .env.example .env

# 2. Fill .env with real values. Non-negotiables:
#    APP_ENV=production, DEBUG=false,
#    SECRET_KEY=$(openssl rand -hex 32),
#    strong POSTGRES_PASSWORD + REDIS_PASSWORD,
#    CORS_ORIGINS=["https://<your-domain>"],
#    real LLM/Azure credentials, feature flags all false initially.

# 3. Bring the stack up — the migrate service runs `alembic upgrade head`
#    and the backend only starts after it exits 0.
docker compose -f docker-compose.prod.yml up --build -d

# 4. Seed RBAC roles/permissions (first time only; idempotent):
docker compose -f docker-compose.prod.yml exec backend \
  uv run python -m scripts.seed_enterprise

# 5. Verify:
curl -fsS http://localhost:8000/api/v1/health          # liveness
curl -fsS http://localhost:8000/api/v1/health/ready    # DB + Redis checks
```

TLS terminates in front of the frontend nginx (platform LB or a reverse
proxy). Once TLS is live, uncomment the HSTS header in `frontend/nginx.conf`.

## Upgrades

```bash
git fetch --tags && git checkout vX.Y.Z
docker compose -f docker-compose.prod.yml up --build -d   # migrate runs first
curl -fsS http://localhost:8000/api/v1/health/ready
```

Migrations are expand-contract: every revision has a tested downgrade
(`skills/playbooks/database-migrations.md`). The backend starting is gated on
`migrate` exiting 0 — a failed migration halts the rollout with the old
containers still on the previous image (see `rollback-plan.md`).

## Feature-flag rollout order (staged)

All agentic flags ship OFF. Recommended enablement sequence, one at a time,
with `docs/development/agentic-local-testing.md` as the validation script:

1. `FEATURE_VECTOR_RETRIEVAL` (needs embedding provider + backfill script;
   degrades to keyword safely).
2. `FEATURE_AGENT_TOOLS` (local read-only tools).
3. `FEATURE_MCP_TOOLS` + `MCP_USE_MOCK=false` + per-server allow-list.
4. `REMOTE_SUPPORT_USE_MOCK=false` (real Remote Help; verify
   `GET /remote-support/provider/health`).
5. `FEATURE_AGENT_WRITE_ACTIONS`, then `FEATURE_BACKGROUND_AGENTS` last.

## Secrets handling

- `.env` never enters version control (gitignored); production values come
  from the deployment platform's secret store.
- `REMOTE_HELP_CLIENT_SECRET`, `MCP_*_TOKEN`, `AZURE_OPENAI_API_KEY` are
  secrets-manager values, injected as env vars at deploy time.
- Rotating `SECRET_KEY` invalidates all sessions — schedule in a window.
