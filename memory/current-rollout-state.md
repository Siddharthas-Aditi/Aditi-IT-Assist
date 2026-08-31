# Current Rollout State

Snapshot of what's shipped, flagged, stubbed, or deferred. **Update this file whenever
you change flag state, ship a stubbed area, or add a phase.** Cross-check the
"Implementation Status" table in `CLAUDE.md`.

_Last synced from repo: 2026-08-31 (UAT foundation-hardening iteration —
migrations through `015_ticket_number_sequence`; supervisor remains shadow-only)._

## Shipped & on by default
- FastAPI backend, JWT local auth (login/register/me/logout/refresh), RBAC (5 roles).
- **Session hardening (2026-07)**: refresh-token rotation with jti Redis denylist,
  real logout revocation, refresh-tokens-can't-authenticate-APIs, typed 503 when
  fail-closed (`TOKEN_DENYLIST_FAIL_CLOSED`, default fail-open). `core/token_store.py`.
- **Rate limiting (real, 2026-07)**: Redis sliding window + in-memory fallback,
  tighter auth bucket, health/metrics exempt. `core/rate_limit.py`. Off in tests via conftest env.
- **Production boot validation**: `Settings.validate_production()` — refuses to start
  with placeholder SECRET_KEY, DEBUG=true, dev DB password, empty REDIS_PASSWORD,
  localhost CORS, mock/flag mismatches. Wired in lifespan (fail fast).
- **Observability**: structured `http_request` access log + Prometheus metrics at
  `/api/v1/health/metrics` (`METRICS_ENABLED`), real readiness probe (DB+Redis, 503),
  optional OTEL tracing (`OTEL_ENABLED`). Security headers middleware + nginx headers/CSP.
- Ticket lifecycle + SLA; LangGraph workflow (6 nodes + supervisor shadow).
- Conversational intent classifier (hybrid LLM + keyword); typed specialist
  definitions are available for evaluation, but primary specialist dispatch is
  not yet enabled in the employee chat graph.
- Grounded published-only retrieval + citations (keyword path default).
- Knowledge management + governance + improvement loop (review-gated).
- Controlled web fallback (registry opt-in, trust-tier filtered, candidate-creating).
- Live specialist chat (idle policy, typing indicators, same-window handoff, queue
  notifications); specialist queue + atomic claim + handoff package.
- Chat-escalation artifacts (immutable snapshot + context), summary-first handoff view.
- **Remote support workflow (end-to-end, 2026-07)**: consent-gated session lifecycle +
  **live-chat bridge** (`POST /specialist-chat/{id}/remote-session`, linkage
  chat→ticket→remote session), employee consent surfacing anywhere in the employee
  workspace (`GET /remote-support/consent/pending` + `ConsentWatcher` in EmployeeLayout),
  **session sweeper** (consent expiry + max-duration termination), provider prereq gate.
  ADR: `docs/architecture/remote-support-decision.md` (Remote Help primary; no fake
  session API — admin-center launch URL + in-client code exchange; TeamViewer documented
  alternative).
- Analytics API, audit logging, background scheduler (idle + remote-session sweepers),
  Docker Compose, Alembic migrations 001–015, admin console.
- Post-chat feedback system.
- **Durable AI chat sessions (2026-07-22)**: migration ``012`` upgrades the
  bootstrap ``support_sessions``/``messages`` schema to the durable contract.
  ``SupportSessionService`` mirrors each successful chat
  turn; ``GET /chat/sessions*`` implemented; tickets link via ``session_id``;
  ``PostChatFeedbackCard`` wired in employee chat on resolution.
- **Deploy mechanics (2026-07)**: prod compose `migrate` one-shot service gates backend
  start; **alembic.ini `version_locations` fix** (upgrade head previously applied NOTHING);
  Redis password required (`:?` interpolation); release workflow publishes tagged images
  to GHCR behind the full CI gate. Runbooks in `docs/deployment/`.

## Behind feature flags (default OFF in code)
| Flag | What it enables | Phase | Key docs |
|------|-----------------|-------|----------|
| `FEATURE_VECTOR_RETRIEVAL` | Hybrid vector+keyword retrieval | 6 | `retrieval-and-indexing.md` |
| `FEATURE_AGENT_TOOLS` | Typed local read-only tools + runtime | 5 | `agent-tooling.md` |
| `FEATURE_MCP_TOOLS` | MCP-backed read tools (Graph, ServiceNow) | 7 | `mcp-integrations.md` |
| `FEATURE_AGENT_WRITE_ACTIONS` | Human-approved write tools | 8 | `agent-write-actions-and-tasks.md` |
| `FEATURE_BACKGROUND_AGENTS` | Async autonomous task runner | 8 | `agent-write-actions-and-tasks.md` |
| `MCP_USE_MOCK` (dev true) | Mock MCP sessions for local governance testing | 7 | `agentic-local-testing.md` |
| `REMOTE_SUPPORT_USE_MOCK` (dev true) | Mock remote-support provider; false = real Graph-backed Remote Help (needs `REMOTE_HELP_*` creds) | — | `remote-support-decision.md` |

Prereqs: vector retrieval needs an embedding provider configured + `scripts/backfill_embeddings.py` run; otherwise it degrades to keyword. Staged enablement order: `docs/deployment/production-deployment.md`.

## Stubbed / scaffolded (not yet functional)
- **SAML SSO** — endpoints exist; IdP call is `pass`. (`saml-roadmap.md`)
- **WebSocket chat** — HTTP polling today; API shape supports drop-in upgrade.
- **Knowledge Candidate review UI** — backend ready; SME UI deferred.
- **Cross-tab BroadcastChannel logout** — each tab runs its own idle timer.
- **Refresh-token reuse *detection*** — rotation ships; automatic family-revocation on
  replay is deferred (replay currently just 401s).
- **Human Support Copilot** — spec only (`agents/08-copilot.md`).

## Roadmap / priorities
- Iteration of record: `plans/production-readiness-2026-07.md` (gap analysis + status).
- Roadmap: `plans/agentic-ops-platform-evolution.md` (Phases 5–8+),
  `plans/phase1-hardening.md`, `plans/chat-escalation-artifacts.md`,
  `plans/admin-console-redesign.md`.
- Near-term: promote flagged phases mock→real, approval queue UI, KB candidate review UI,
  SAML SSO, refresh-reuse detection, notification channels beyond in-app (email/push)
  for remote-support consent.

## Seeded team users (`scripts/seed_enterprise.py`, auto on startup)
`hareesh@aditiconsulting.com`/`Hareesh@2026` (it_admin),
`sagar@aditiconsulting.com`/`Sagar@2026` (it_lead),
`madhukar@aditiconsulting.com`/`Madhukar@2026` (it_lead),
`siddhartha@aditiconsulting.com`/`Siddhartha@2026` (employee),
`naresh@aditiconsulting.com`/`Naresh@2026` (employee).
Re-run `seed_enterprise` (or restart backend with `SEED_ON_STARTUP=true`) after
permission changes.
