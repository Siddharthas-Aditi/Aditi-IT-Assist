# Release Checklist

For cutting a deployable build of Aditi IT Assist. Pair with `DEPLOYMENT_GUIDE.md`.

## Pre-release gate
- [ ] `main` is green in CI (`.github/workflows/ci.yml`).
- [ ] Full suite passes locally: `make test` + `make lint` + `make typecheck`.
- [ ] All eval datasets pass (retrieval, tool-routing, mcp-contract, action-safety).
- [ ] No open items in `memory/known-risks.md` regressed by this release.

## Database & config
- [ ] All migrations apply cleanly on a fresh DB (`make db-migrate`) and each has a
      tested `downgrade`. Migration order 002→current is contiguous.
- [ ] `seed_enterprise` runs clean; re-seed required after new permissions is documented.
- [ ] `.env.example` documents every new setting; no real secrets committed.
- [ ] Feature-flag state for the release is intentional and recorded in
      `memory/current-rollout-state.md` (default off unless deliberately enabling).

## Integrations & flags
- [ ] Any flag being turned on has its real integration wired (not mock) — e.g. embedding
      provider for `FEATURE_VECTOR_RETRIEVAL`; `MCP_USE_MOCK=false` only with real creds.
- [ ] Write actions / background agents remain governed (approval + audit) if enabled.

## Build & smoke
- [ ] `docker compose up --build` brings all 4 services healthy (`make docker-ps`).
- [ ] `make smoke-test` passes; `/api/v1/health` OK; frontend loads; login works for each role.
- [ ] Manual sanity of critical flows: employee chat → escalation → specialist handoff;
      queue claim + live chat; admin user/audit views.

## Docs & comms
- [ ] `CLAUDE.md` implementation-status table + `memory/current-rollout-state.md` current.
- [ ] Release notes / changelog written; breaking changes and migration steps called out.
- [ ] Rollback plan confirmed (previous image + `db-downgrade` path).

## Post-release
- [ ] Verify health, error rates, and audit logging in the target environment.
- [ ] Tag the release; record the deployed flag configuration.
