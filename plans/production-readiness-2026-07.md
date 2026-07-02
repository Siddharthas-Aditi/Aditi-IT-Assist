# Production Readiness — Gap Analysis & Iteration Plan (2026-07)

> Audit date: 2026-07-02. Baseline: backend 838 passed / 0 failed / 1 skipped
> (after fixing two test-isolation bugs, see §4). Migrations through `009`,
> `REGISTRY_VERSION 1.2.0`. This plan is the working document for the
> production-hardening iteration; keep it updated as items land.

## 1. Verdict

The platform is architecturally sound (typed contracts, versioned registries,
service-layer enforcement, eval gates) but **not yet deployable to production**.
Blockers are concentrated in four areas: deploy mechanics, auth/session
hardening, observability, and the remote-support provider (mock-only).

## 2. Gap analysis (ranked)

### P0 — deploy fails or is unsafe without these
| # | Gap | Evidence | Fix |
|---|-----|----------|-----|
| 1 | No migration-on-deploy: prod containers start against an unmigrated DB | `backend/Dockerfile` CMD runs uvicorn directly; no migrate service in `docker-compose.prod.yml` | Dedicated `migrate` one-shot service; backend `depends_on: service_completed_successfully` |
| 2 | No production config validation: app boots with `SECRET_KEY=change-me-in-production`, `DEBUG=true` | `app/core/config.py` defaults; no lifespan check | `Settings.validate_production()` — fail fast in lifespan when `APP_ENV=production` |
| 3 | Logout is a no-op; tokens live 24 h after logout | `auth.py` `# TODO: Implement token blacklisting` | Redis jti denylist + check in auth dependency; refresh rotation with old-token revocation |
| 4 | Rate limiting is config-only (stub) | `RATE_LIMIT_ENABLED` exists; no middleware anywhere | Real sliding-window middleware (Redis-backed, in-memory fallback), health endpoints exempt |
| 5 | Redis password defaults to empty in prod compose | `docker-compose.prod.yml` `requirepass ${REDIS_PASSWORD:-}` | Require non-empty in prod; wire `REDIS_PASSWORD` through Settings/REDIS_URL |
| 6 | No image publish / release pipeline | `.github/workflows/ci.yml` builds but never pushes | Release workflow: build, tag, push to GHCR on version tags |

### P1 — production-degrading
| # | Gap | Evidence | Fix |
|---|-----|----------|-----|
| 7 | Readiness probe returns hardcoded `ready` (no DB/Redis check) | `api/v1/health.py` | Real dependency checks |
| 8 | Telemetry is a stub (no metrics/tracing) | `core/telemetry.py` TODO | Prometheus metrics endpoint + request-timing middleware; OTEL opt-in |
| 9 | No security headers (API or nginx) | `main.py`, `frontend/nginx.conf` | Header middleware + nginx headers |
| 10 | Remote-support provider is mock-only; no chat/ticket wiring, no notification, no timeout sweeper | `providers/microsoft_remote_help.py` STUB; `support_session_id` never populated | See `docs/architecture/remote-support-decision.md` (ADR) + §3 |
| 11 | No ops runbooks (deploy, rollback, monitoring, staging validation) | `docs/deployment/` doesn't exist | Write them |

### P2 — accepted for launch, tracked
- SAML SSO stub (local JWT auth is the launch path; roadmap `docs/security/saml-roadmap.md`).
- WebSocket chat (polling works; API shape supports drop-in upgrade).
- KB candidate review UI (backend ready; SME flow via API/admin for now).
- Cross-tab BroadcastChannel logout.
- Refresh-token *reuse detection* (rotation itself lands in this iteration).

## 3. Remote support decision (summary — full ADR in docs/architecture/remote-support-decision.md)

**Chosen: Microsoft Remote Help (Intune-native) as primary provider**, behind the
existing `RemoteSupportProvider` abstraction; TeamViewer (new Tensor connector)
documented as the alternative for devices outside Intune management.

Key facts driving the decision (verified 2026-07-02):
- The legacy Intune TeamViewer connector is deprecated (retires April 2027);
  the replacement connector requires TeamViewer Tensor licensing and devices
  actively managed by TeamViewer — a second management plane we don't have.
- There is **no public Graph API that creates attended Remote Help sessions**;
  sessions launch from the Intune admin center or Remote Help app with code
  exchange. Graph exposes `remoteAssistanceSettings` (beta) and managed-device
  lookups, which we use for prereq validation and health.
- Aditi is already Microsoft-centric here: Entra/Intune/Exchange MCP tools,
  Azure OpenAI, Office 365 SMTP.

Consequence: the provider is an **honest orchestrator** — our platform owns
consent, RBAC, audit, ticket/chat linkage, and timers; Remote Help owns the
pixel transport (Entra-authenticated, Intune-policied). No fake session API.

## 4. Fixes already landed in this iteration
- `tests/api/test_endpoints.py::test_stats_accessible_to_admin` — mocked
  `AdminStatsService` (RBAC test was coupled to a live Postgres).
- `tests/unit/test_azure_llm.py::test_complete_passes_api_base_and_version` —
  settings patch now spans the call, not just construction.

## 5. Iteration order
1. ✅ Audit + this gap analysis.
2. Security/config blockers (P0 #2–5): Settings validation, jti denylist +
   refresh rotation, rate limiting, Redis auth.
3. Deploy mechanics (P0 #1, #6): migrate service, release workflow.
4. Observability + headers (P1 #7–9).
5. Remote support (P1 #10): real provider (validate/launch/terminate via
   Graph + admin-center launch URLs), live-chat/ticket wiring, consent
   surfacing, expiry sweeper, `REMOTE_SUPPORT_USE_MOCK` for dev.
6. Tests for every new surface; full suite green.
7. Runbooks + docs + memory/CLAUDE.md sync; final readiness checklist.

## 6. Loop control
Bounded loops per repo policy: same failure twice with same root cause ⇒ stop
and report blocker. No completion claims without a passing run recorded here.

## 7. Iteration log (2026-07-02)

**Shipped this iteration** (backend suite: 838 → **891 passed, 0 failed**;
frontend tsc + eslint clean):

- P0 #2 — `Settings.validate_production()` + lifespan fail-fast; tests
  parameterize every violation. (`core/config.py`, `main.py`)
- P0 #3 — jti Redis denylist (`core/token_store.py`), logout revocation,
  refresh rotation w/ old-token revocation, and a **found security bug
  fixed**: refresh tokens previously authenticated API calls
  (`validate_session` had no `type` check) and shared the access token's
  jti + 24h expiry. Frontend already handles rotated refresh tokens.
- P0 #4 — real rate limiting (`core/rate_limit.py`): Redis sliding window,
  in-memory fallback, auth-bucket budget, health/metrics exempt.
- P0 #5 — Redis `requirepass` mandatory in prod compose (`:?` interpolation),
  `REDIS_PASSWORD` in Settings/REDIS_URL + boot validation.
- P0 #1 — `migrate` one-shot service gating backend start; **found deploy bug
  fixed**: `alembic.ini` lacked `version_locations`, so `upgrade head`
  silently applied zero migrations.
- P0 #6 — `.github/workflows/release.yml` (CI gate → GHCR images on tags →
  draft release notes); `ci.yml` now `workflow_call`-reusable.
- P1 #7 — readiness probe does real DB `SELECT 1` + Redis `PING`, 503 gates.
- P1 #8 — `RequestMetricsMiddleware` (structured access log + Prometheus at
  `/api/v1/health/metrics`), OTEL opt-in in `core/telemetry.py`.
- P1 #9 — `SecurityHeadersMiddleware` + nginx CSP/security headers +
  metrics blocked at the public vhost.
- P1 #10 — remote support end-to-end: real Graph-backed Remote Help adapter
  (+ honest no-session-API design per ADR), mock provider split out
  (`REMOTE_SUPPORT_USE_MOCK`), single factory, provider prereq gate,
  session sweeper (consent expiry + max duration), live-chat bridge
  endpoint + system message, employee `ConsentWatcher` (consent modal on
  any employee page), `GET /remote-support/consent/pending`,
  `support_session_id` linkage.
- P1 #11 — runbooks: `docs/deployment/{production-deployment,rollback-plan,
  monitoring-guide,staging-validation}.md`.
- Tests added: `test_security_hardening.py` (29), `test_remote_support_providers.py`
  (15), `test_remote_support_chat_bridge.py` (8), readiness-probe API tests;
  two pre-existing test-isolation bugs fixed.
- Docs/memory synced: CLAUDE.md status table, `memory/current-rollout-state.md`,
  `docs/architecture/remote-support.md`, ADR, `.env.example`.

**Known residuals** (tracked, non-blocking):
- Repo-wide pre-existing ruff 0.15 debt (~460 findings incl. N802 config
  properties, N818 exception names) — new code is clean; schedule a
  dedicated lint-debt pass or pin ruff in uv.lock.
- Frontend vitest not runnable in this sandbox (darwin node_modules on a
  linux mount); CI's `npm ci` path covers it.
- Refresh-token *reuse detection*, SAML SSO, WebSocket chat, KB candidate
  review UI, consent notification channels beyond in-app (email/push) —
  see rollout-state "Stubbed".
