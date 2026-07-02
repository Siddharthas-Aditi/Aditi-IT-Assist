# Rollback Plan

Every release is a tagged, immutable image pair in GHCR, so rollback is
"deploy the previous tag". Migrations are the only stateful step; handle
them explicitly.

## Application rollback (no schema change involved)

```bash
git checkout vX.Y.(Z-1)         # or: export IMAGE_TAG in your deploy tooling
docker compose -f docker-compose.prod.yml up --build -d
curl -fsS http://localhost:8000/api/v1/health/ready
```

Data written by the newer version remains; the API contract is
backward-compatible within a minor series (typed Pydantic schemas + versioned
contracts — breaking a schema requires a version bump per repo policy).

## Migration failure during rollout

The `migrate` service failing stops the rollout **before** the new backend
starts — the previous containers keep serving. Actions:

1. Read the migrate container logs: `docker compose -f docker-compose.prod.yml logs migrate`.
2. Fix forward if trivial (config/permission issue), else abort the release.
3. No `alembic downgrade` is needed when the upgrade itself failed —
   Alembic runs each revision in a transaction on Postgres.

## Rolling back past an applied migration

Only needed when a bad release ran for a while and the schema must revert:

```bash
docker compose -f docker-compose.prod.yml run --rm migrate \
  uv run alembic downgrade <previous_revision>
```

Every revision ships a tested downgrade (`known-risks.md` §7). Take a
`pg_dump` snapshot first; downgrades that drop columns lose that data by
definition:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U "$POSTGRES_USER" -Fc aditi_assist > pre-rollback.dump
```

## Feature-flag rollback (preferred for agentic features)

Phases 5–8 and real remote support are flag-gated. The cheapest rollback for
misbehavior in those areas is flipping the flag off and restarting the
backend — no image change, no migration:

| Symptom | Flip off |
|---|---|
| Bad tool-calling behavior | `FEATURE_AGENT_TOOLS` |
| Retrieval quality regression | `FEATURE_VECTOR_RETRIEVAL` |
| MCP integration errors | `FEATURE_MCP_TOOLS` (or remove the server id) |
| Remote Help issues | `REMOTE_SUPPORT_USE_MOCK=true` (or disable UI use) |
| Write-action concerns | `FEATURE_AGENT_WRITE_ACTIONS` |
| Background agent load | `FEATURE_BACKGROUND_AGENTS` |

## Session invalidation after a security incident

Rotate `SECRET_KEY` (invalidates every access + refresh token instantly) and
restart. For a single compromised account, disable the user in the admin
console — refresh explicitly re-checks `is_active`.
