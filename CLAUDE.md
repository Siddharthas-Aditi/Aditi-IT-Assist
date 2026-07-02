# CLAUDE.md - AI Agent Instructions for Aditi IT Assist

> **Purpose**: This is the master context file for AI coding assistants (Claude, Copilot, etc.)
> working on this codebase. Read this first before making any changes.

> **AI Development Framework (start here).** This repo ships a project-specific operating
> system for AI-assisted development. At the start of a session, load context from
> **`memory/`** (`project-overview`, `architecture-map`, `domain-model`, `feature-map`,
> `known-risks`, `glossary`, `current-rollout-state`). Follow the process in
> **`docs/development/engineering-workflow.md`** and validate with
> **`docs/development/commit-checklist.md`**. Use task playbooks in **`skills/playbooks/`**
> and role guides in **`agents/dev/`**. Safety gates: **`docs/development/safety-gates.md`**.
> Full index: **`docs/development/ai-development-framework.md`**. Everything below remains the
> authoritative rulebook; the framework docs are the progressive-disclosure layer beneath it.

---

## Project Overview

**Aditi IT Assist** is an enterprise-grade internal IT service platform for Aditi Consulting.
It uses a multi-agent workflow (LangGraph) to intake employee IT issues, classify them,
retrieve relevant knowledge, guide troubleshooting, and escalate when needed.

**Enterprise capabilities include:**
- Role-based access control (employee, it_agent, it_lead, it_admin, security_auditor)
- Future-ready SAML SSO integration (pluggable auth providers)
- Enterprise ticket lifecycle with SLA tracking
- Remote assistance orchestration (Microsoft Remote Help integration ready)
- Analytics dashboards for IT leadership
- Audit logging and compliance controls
- Live agent support workflow

## Architecture Quick Reference

| Layer | Technology | Location |
|-------|-----------|----------|
| Backend API | Python 3.12+ / FastAPI / SQLAlchemy | `backend/` |
| AI Orchestration | LangGraph / LiteLLM | `backend/app/workflows/` |
| Auth & RBAC | JWT / Pluggable Providers / SAML stub | `backend/app/services/auth/` |
| Database | PostgreSQL 16 / pgvector | Docker (port 5432) |
| Cache | Redis 7 | Docker (port 6379) |
| Frontend | React 18 / TypeScript / Vite | `frontend/` |
| UI System | Tailwind CSS / shadcn/ui / Radix | `frontend/src/components/` |
| Package Mgmt | uv (backend) / npm (frontend) | `pyproject.toml` / `package.json` |

## Key Enterprise Patterns

### Authentication
- Pluggable provider: `app/services/auth/providers/base.py`
- Local auth: `app/services/auth/providers/local.py`
- SAML stub: `app/services/auth/providers/saml.py`
- Dependencies: `app/services/auth/dependencies.py`

### Authorization
- Role guards: `require_roles("it_agent", "it_lead", "it_admin")`
- Permission guards: `require_permissions("ticket:assign")`
- Type aliases: `CurrentUser`, `ITAgentUser`, `ITLeadUser`, `AdminUser`

### Data Isolation
- Employees see ONLY their own data (tickets, chats)
- Internal notes hidden from employees
- Audit logs restricted to admin/auditor roles

### Knowledge Management
- Structured, governed articles with a lifecycle: `draft → in_review → approved → published → archived`
- **The chat agent retrieves published articles only** (`KnowledgeRetrievalService`); drafts are never exposed to employee chat
- Three boundaries: KB management (`services/knowledge/management.py`), KB retrieval (`retrieval.py`), indexing (`indexing.py`)
- Per-action lifecycle permissions enforced in the service; coarse API gating via `require_permissions(knowledge:*)`
- Publish triggers indexing; archive removes from the index; both snapshot a version
- Docs: `docs/architecture/knowledge-management.md`, `docs/architecture/retrieval-and-indexing.md`, `docs/product/knowledge-workflow.md`, `docs/security/knowledge-access-control.md`

### Grounded Troubleshooting (chat agent)
- The chat agent must behave like a real IT analyst: identify the **issue subtype**, retrieve **only relevant** knowledge, track tried steps, **advance on failure**, and escalate when grounded help is exhausted. It must **never mix unrelated KB content** (this fixed the "inbox full → password reset / Windows Update / repeated steps" bug).
- Three non-prompt enforcement points:
  - **Subtype classification**: `app/services/agents/subtype_classifier.py` (deterministic; sets `DiagnosticContext.issue_subtype`, e.g. `mailbox-full`; vague → `None` → ask).
  - **Retrieval guardrail**: `app/services/agents/grounding.py` `ground_results` (wired in `workflows/nodes/retrieval.py`) — rejects cross-family articles, reranks the subtype match first, returns a kept/rejected trace.
  - **Composite confidence**: `app/services/agents/confidence.py` — confidence can't be high without grounding; loop/unresolved penalties apply.
- Loop control / tried-step memory: `DiagnosticContext.suggested_steps`/`failed_steps` + `workflows/nodes/resolution.py` `_build_progression` (present only NEW steps; never repeat a failed batch; escalate when exhausted). Context is persisted across turns by `ChatService`.
- KB rule: each article's `subcategory` MUST equal a real subtype from `subtype_classifier.known_subtypes(category)`; keep steps scoped to that subtype. No monolithic "all issues" articles.
- IT/admin-only `debug` trace on the chat response (employees never get it).
- **Escalation → ticket → live agent**: when grounded help is exhausted (or the user asks for a human), the agent *offers* to raise a ticket; a real ticket is persisted **only on explicit confirmation** ("Connect with a specialist" → `POST /chat/request-live-agent`, or typed "yes"), and always **before** the human handoff. Persistence is in the service layer (`ChatService._handle_ticketing` / `request_live_agent`), not the workflow nodes — `ticketing.py` only builds a draft + offer. Idempotent per session. See `docs/architecture/escalation-and-live-agent-handoff.md`.
- **No-direct-connect policy**: a user can't reach a live specialist (or create the anchoring ticket) before a minimally-useful problem statement is captured. One pure policy — `app/services/agents/escalation_policy.py::handoff_context_sufficient` — gates two points: the triage `ESCALATE_REQUEST` path (`_gather_problem_before_handoff` asks for details, no escalation) and `ChatService.request_live_agent` (returns the gather prompt with `ticket=None`). Once context exists, the AI-first flow runs and the user can request a human any time. See `docs/architecture/chat-to-live-handoff.md`.
- **Same-window handoff + waiting state**: employee chat polls `GET /specialist-chat/active`; while queued it shows "Please wait while I connect you to a live IT specialist", then flips to "An IT specialist has joined" and continues in the same `LiveChatPage` (no popup). Transcript persists + resumes on refresh.
- **Idle policy (live chat)**: default **7-minute warning + 2-minute grace** → auto-end (`ended_by_timeout`). Config `LIVE_CHAT_IDLE_WARNING_SECONDS`/`LIVE_CHAT_IDLE_END_SECONDS` or per-`start` override; pure `evaluate_idle` shared by the polling endpoint + 30s background sweeper; any message resets it (typing does not).
- **Typing indicators (both ways)**: in-memory, ephemeral (`specialist_chat_service._typing_state`, 8s TTL); `POST /specialist-chat/{id}/typing` (no DB/audit, no idle reset); `GET /specialist-chat/{id}` returns `typing` = roles typing excluding the caller.
- **Specialist notification**: `LiveQueuePage` chimes (Web Audio) + desktop-notifies once per *new* unclaimed handoff (tracks seen ticket ids; mute toggle), via `frontend/src/lib/notification-sound.ts`.
- Docs: `docs/architecture/chat-grounding-rules.md`, `docs/architecture/retrieval-guardrails.md`, `docs/architecture/troubleshooting-state-machine.md`, `docs/architecture/escalation-and-live-agent-handoff.md`, `docs/architecture/chat-to-live-handoff.md`, `docs/architecture/live-chat-session-lifecycle.md`, `docs/architecture/idle-timeout-and-typing-indicators.md`, `docs/product/chat-and-live-support-flow.md`, `docs/development/chat-debugging-guide.md`, `docs/development/golden-conversations.md`, `docs/development/live-chat-qa-checklist.md`

### Chat-Escalation Artifacts (transcript snapshot + escalation context)
- When an unresolved AI chat escalates, the system creates **two linked, immutable artifacts** so the specialist continues without the employee repeating anything. The ticket is the parent operational object; full context lives in linked structured records — **never** a raw chat blob in the ticket description.
  - **Transcript snapshot** (`transcript_snapshots`): write-once, ordered Employee↔AI history captured at escalation. Immutable by contract — `EscalationService` has no update path and `extract_transcript()` returns a copy, so later session mutations can't reach it. Post-escalation human↔human messages stay in `specialist_chat_messages` (never mixed in).
  - **Escalation context** (`escalation_contexts`, one per ticket): structured handoff payload — issue summary, problem statement, detected intent, category/subtype, affected system, `ai_attempted_steps[]`, `kb_articles_referenced[]`, `kb_gap_tags[]`, `ai_confidence`, `ai_resolution_status`, `escalation_reason`, routing, `supervisor_decision_trace`, `diagnostic_slots`, plus **resolution-comparison** fields filled at resolve time (`specialist_resolution_summary/steps`, `final_resolution_category`, `ai_vs_specialist_resolution_gap`, `kb_candidate_flag`).
- **Models**: `app/models/escalation.py`. **Migration**: `009_chat_escalation_artifacts`. **DTOs**: `app/schemas/escalation.py` (incl. `SpecialistHandoffView` — summary first, transcript second). **Service**: `app/services/escalation_service.py` (`create_escalation_artifacts`, `get_handoff_view`, `record_resolution_comparison`; idempotent per ticket; audited).
- **KB gap tags**: typed controlled vocabulary + pure `derive_kb_gap_tags()` in `app/services/agents/kb_gap_tags.py` (`KB_GAP_TAG_VOCAB_VERSION`). Tags: `no_matching_article`, `article_suggested_but_unresolved`, `specialist_only_resolution_needed`, `unclear_problem_statement`, `repeated_escalation_pattern`, `missing_runbook`, `policy_or_access_exception`.
- **Creation wiring**: `ChatService._persist_and_queue` → `_create_escalation_artifacts` (atomic with ticket create + queue; best-effort, never blocks handoff). Employee gets an explicit "I'm sharing our conversation so you don't repeat everything" confirmation.
- **Specialist consumption**: `SpecialistQueueService.build_handoff_package` reads the persisted context first (survives restart; fixed the old data-starved package). New endpoints: `GET /specialist-queue/{id}/handoff-view`, `GET /specialist-queue/{id}/escalation-context`, `POST /specialist-queue/{id}/resolution-comparison`. Frontend: `features/specialist-chat/HandoffContextPanel.tsx` (summary-first, collapsible transcript, role-distinct bubbles) in `LiveChatPage` + breadcrumbs.
- **Improvement loop is human-reviewed only** — resolution-comparison data feeds SME-reviewed KB candidates / prompt tuning; **no uncontrolled self-learning**.
- Docs: `docs/architecture/chat-escalation-artifacts.md`, `docs/architecture/transcript-snapshot-and-context-model.md`, `docs/product/chat-to-ticket-handoff.md`, `docs/product/specialist-triage-experience.md`, `docs/development/chat-escalation-qa-checklist.md`. Plan: `plans/chat-escalation-artifacts.md`.

### Agent Tool Calling (Phase 5 — behind `FEATURE_AGENT_TOOLS`, default off)
- Lets specialists *act*, not just return canned steps. Every tool is a typed, versioned, declarative `ToolSpec` (Pydantic args/result, `side_effect`, `required_permissions`, `approval`); nothing callable that isn't declared. Mirrors the `AGENT_REGISTRY` discipline.
- **Single enforcement point**: `app/services/agents/tools/runtime.py` `AgentToolRuntime.dispatch` runs every call through allow-list → existence → arg validation → RBAC → **approval gate** → execute, and audits every path (including rejections). `run_loop` is the bounded (≤8) LLM tool-use loop. Read-only/no-dependency on LLM or DB → fully unit-testable.
- **Tool registry**: `app/services/agents/tools/registry.py` `TOOL_REGISTRY` + `TOOL_REGISTRY_VERSION`, enumerated not dynamic. Phase-5 tools (all read-only, no approval): `kb_search`, `mailbox_quota_estimate`, `ticket_draft`. `ticket_draft` never persists.
- **Per-agent allow-list**: `SpecialistAgentSpec.allowed_tools` (`REGISTRY_VERSION` → `1.1.0`). Outlook is the reference: tool path activates only when the flag is on, an LLM is configured, AND an authorized `SpecialistInput.tool_context` is supplied — otherwise the deterministic step path runs unchanged. Tool-path failure falls back to deterministic (never regresses).
- **LLM**: `LLMService.complete_with_tools` does tool *selection* only; enforcement is the runtime's job. Write/destructive + `human` approval machinery is implemented and tested (synthetic `reset_mfa` probe) but unused until Phase 8.
- Eval/gate: `backend/tests/data/tool_routing_eval.yaml` + `tests/unit/test_tool_routing_eval.py` (0-unauthorized gate, contract pins); unit tests `tests/unit/test_agent_tools.py`, `tests/unit/test_outlook_tool_path.py`.
- Docs: `docs/architecture/agent-tooling.md`; roadmap `plans/agentic-ops-platform-evolution.md` (Phase 5).

### Semantic + Hybrid Retrieval (Phase 6 — behind `FEATURE_VECTOR_RETRIEVAL`, default off)
- Replaces keyword-only ranking with a **hybrid blend** (vector + keyword + usage + quality) when an embedding provider is configured; otherwise unchanged keyword path.
- **Pure ranking core**: `app/services/knowledge/ranking.py` (`RANKING_VERSION`) — `cosine_similarity`, `keyword_overlap_score`, `hybrid_score`, `rank()`. Weights sum to 1.0, tunable via `HYBRID_WEIGHT_*` config. **Keyword floor**: with no vector signal the vector weight folds into keyword, so hybrid never scores below keyword.
- **Vector query**: `KnowledgeRepository.article_vector_scores` — pgvector `cosine_distance` aggregated to best-chunk similarity per published article. `KnowledgeRetrievalService.search` embeds the query, blends, sets `source=db_hybrid` (else `db_keyword`). Degrades to keyword on no provider / embed error / no embedded chunks; invalid weights fall back to defaults — never fails a request.
- **Honest indexing**: `indexing.py` marks a chunk `indexed` only when it actually has a vector (else `pending`); article `indexed` only when all chunks embedded. `backfill_embeddings()` + `scripts/backfill_embeddings.py` populate vectors for pre-existing content.
- Eval/gate: `backend/tests/data/retrieval_eval.yaml` + `tests/unit/test_retrieval_eval.py` (keyword baseline recall@k target; **hybrid ≥ keyword** recall@k). Unit: `test_hybrid_ranking.py`, `test_vector_retrieval.py`.
- Docs: `docs/architecture/retrieval-and-indexing.md`; roadmap `plans/agentic-ops-platform-evolution.md` (Phase 6).

### MCP Integrations (Phase 7 — behind `FEATURE_MCP_TOOLS`, per-server, default off)
- Agents *consume* external systems (Microsoft Graph for Entra/Intune/Exchange, ServiceNow) as MCP-backed tools, surfaced into the same `AgentToolRuntime` as local tools — identical allow-list/RBAC/approval/audit. Read-only in Phase 7; writes are Phase 8.
- **Declarative server allow-list**: `app/services/agents/mcp/profiles.py` `MCP_SERVER_REGISTRY` (`MCP_PROFILE_VERSION`) — transport, trust tier, per-server `allowed_tools`, `side_effect_ceiling`, `auth_secret_ref` (never the secret). Only allow-listed tool names become callable; `build_mcp_tools` rejects bindings exceeding the ceiling.
- **Session abstraction**: `mcp/session.py` `McpSession` protocol (the tool layer depends on this, not the SDK) + lazy `SdkMcpSession` + injectable provider — fully unit-testable with a fake session.
- **Typed tools**: `mcp/tools.py` — `entra_account_status`, `intune_device_compliance`, `mailbox_quota_status` (msgraph), `servicenow_incident_lookup` (servicenow). Pydantic args/result; server responses mapped to typed results (unknowns under `raw`, identifiers backfilled). Time-bounded (`MCP_TOOL_TIMEOUT_SECONDS`); timeout/error → typed ERROR → agent degrades to KB-only.
- **RBAC**: typed perms `integration:directory_read`, `integration:ticketing_read` (granted it_agent+). **Audit**: runtime now records `args_hash`/`result_hash` on every tool call.
- Enablement: `build_default_runtime(include_mcp=True)` merges enabled MCP tools; specialists declare them in `allowed_tools` (`outlook`→mailbox_quota_status, `access_mfa`→entra_account_status, `device_intune`→intune_device_compliance). `REGISTRY_VERSION` → `1.2.0`. Re-run `seed_enterprise` for the new permissions.
- Eval/gate: `backend/tests/data/mcp_contract_eval.yaml` + `tests/unit/test_mcp_contract_eval.py` (typed-spec + allow-list + ceiling + 0-unauthorized). Unit: `tests/unit/test_mcp_tools.py`.
- Docs: `docs/architecture/mcp-integrations.md`; roadmap `plans/agentic-ops-platform-evolution.md` (Phase 7).

### Gated Write Actions & Background Agents (Phase 8 — behind `FEATURE_AGENT_WRITE_ACTIONS` / `FEATURE_BACKGROUND_AGENTS`, default off)
- **Write tools** (MCP-backed, all `side_effect=write`, `approval=human`): `entra_unlock_account`, `reset_mfa` (perm `integration:directory_write`), `servicenow_create_incident` (perm `integration:ticketing_write`); each takes an `idempotency_key`. Write perms granted to `it_lead`+ (higher bar than Phase-7 reads). No destructive tools.
- **Two independent gates**: build gate (`FEATURE_AGENT_WRITE_ACTIONS` — `build_mcp_tools` only constructs write tools when on; Phase-7 stays read-only otherwise) and execution gate (runtime returns `needs_approval` and **never executes** a human-gated tool without an approval token — always on).
- **Propose→approve→execute**: `AgentToolRuntime` surfaces `ProposedAction`s + `pending_approvals`; `execute_approved(proposed, ctx, approver_id=…)` re-dispatches the exact captured invocation through the full gate (allow-list, RBAC, audit w/ hashes, idempotency). Approval never bypasses RBAC. **0 unapproved executions** (eval-asserted). Queue-UI affordance is a follow-up.
- **Background agents**: `app/services/agents/tasks/` — typed `AgentTask` + `AgentTaskStore` (in-memory; DB-backed is the seam for multi-instance) + `AgentTaskRunner` (bounded concurrency, retry-then-fail, audit, `run_once`/`run_forever`). Reference handlers: `knowledge_improvement_sweep` (never auto-publishes), `proactive_diagnostics`. Started in the lifespan via `start_background_jobs(background_agents_enabled=…)`. Background actions still flow through `AgentToolRuntime`.
- Eval/gate: `tests/data/action_safety_eval.yaml` + `test_action_safety_eval.py` (0-unapproved gate, RBAC-no-bypass, build gating); `test_agent_task_runner.py`.
- Docs: `docs/architecture/agent-write-actions-and-tasks.md`; roadmap `plans/agentic-ops-platform-evolution.md` (Phase 8).

### Agent Operability Surfaces (API + UI) — for local testing & ops
- **Agent-ops API** `app/api/v1/agent_ops.py` (`/agent-ops`): `GET /status` (flags + retrieval mode + MCP servers + versions; it_agent+), approval queue `GET/POST /approvals` + `POST /approvals/{id}/approve|reject` (propose = it_agent+, approve/reject = it_lead+), background tasks `GET/POST /tasks` (it_lead+). Schemas `app/schemas/agent_ops.py`.
- **Approval queue** `app/services/agents/approvals.py` — in-memory singleton (`get_approval_queue()`); segregation of duties: propose validates + parks (no RBAC), approve runs `AgentToolRuntime.execute_approved` (RBAC enforced against approver, 0 unapproved executions). **Shared task runner** singleton `tasks/factory.py::get_task_runner()` used by both the lifespan loop and the API.
- **Mock MCP** `mcp/mock_session.py` — `MCP_USE_MOCK` (default true in dev) makes `default_session_provider` return a mock session so all MCP read/write tools work locally with full governance and no real Graph/ServiceNow.
- **Chat agent activity**: `ChatDebugInfo` now carries `routed_specialist` (supervisor shadow), `retrieval_source`, and `citations` (IT/admin debug view only).
- **Frontend**: `features/agent-ops/` (React Query), Operations **Approvals** page (`/operations/approvals`), Admin **Agent Operations** page (`/dashboard/agent-ops`), chat debug additions in `features/chat/ChatBubble.tsx`.
- **Local-dev flags** live in `.env`/`.env.example` (all default off in code). **Run/exercise guide: `docs/development/agentic-local-testing.md`.**

### Admin Console
- Admin-focused shell (no cross-workspace "profile switch"). Sections: Analytics, Team Queue, Knowledge Base, User Management, Audit Logs. Routes under `/dashboard/*` (AdminLayout) + `/audit/*`.
- Backend `app/api/v1/admin.py` → services in `app/services/admin/` (`AdminUserService`, `AuditQueryService`, `AdminStatsService`) + `app/schemas/admin.py`. RBAC via `require_permissions` (`admin:manage_users`, `admin:assign_roles`, `admin:view_audit_log`). Every user/role mutation is audit-logged with before/after diffs. Service-layer rule: a user always keeps ≥1 role.
- User Management API: `GET/PATCH /admin/users`, `GET /admin/users/{id}`, `POST/DELETE /admin/users/{id}/roles[/{role}]`, `GET /admin/roles`. Audit API: `GET /admin/audit-log[/facets|/{id}]`. `GET /admin/stats` is real aggregation (was a stub).
- Analytics `_sla_metrics` returns a real `compliance_rate` (None → UI shows "No data", never `NaN%`).
- Frontend feature module `src/features/admin/` (typed React Query hooks); shared `src/components/admin/` (`Breadcrumbs`, `PageHeader`). Every detail/edit/review page renders breadcrumbs. UI gating mirrors the backend via `src/lib/permissions.ts`.
- Docs: `docs/product/admin-console.md`, `docs/architecture/admin-console-architecture.md`, `docs/development/admin-qa-checklist.md`. Tests: `backend/tests/api/test_admin.py`, `frontend/src/components/admin/Breadcrumbs.test.tsx`, `frontend/src/features/admin/components/badges.test.tsx`.

## Build Order (When Implementing Features)

1. Define data models and schemas first
2. Write service layer with proper abstractions
3. Create API endpoints that delegate to services
4. Build workflow nodes that compose services
5. Add frontend pages and wire to API
6. Write tests for the critical path
7. Update documentation

---

## Coding Guardrails

### Python (Backend)

```python
# ✅ CORRECT: Typed, async, service-layer pattern
@router.post("/chat/message", response_model=ChatResponse)
async def send_message(
    data: ChatMessageCreate,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.process_message(data)

# ❌ WRONG: No types, sync, logic in handler
@router.post("/chat/message")
def send_message(request):
    result = db.query(...)  # Never access DB in route handler
    return {"response": call_llm(result)}  # Never call LLM directly
```

**Rules**:
- Use Python 3.12+ features (type hints, match statements where appropriate)
- Follow clean architecture: routes → services → repositories → models
- All API endpoints must use Pydantic v2 schemas for request/response
- Use `async` for all I/O-bound operations
- Service classes must be injectable (dependency injection via FastAPI Depends)
- Never hardcode LLM provider calls — always go through the abstraction layer
- Use structlog for all logging with structured context
- Database queries go through repository layer, never in route handlers
- All environment config via `app.core.config.Settings` (Pydantic BaseSettings)
- Line length: 100 characters max
- Linter/formatter: Ruff

### TypeScript (Frontend)

```typescript
// ✅ CORRECT: Typed props, functional, uses design system
interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [input, setInput] = useState('');
  return (/* JSX using Tailwind + shadcn */);
}

// ❌ WRONG: No types, class component, inline styles
export class ChatInput extends React.Component<any> {
  render() {
    return <div style={{color: 'red'}}>...</div>;
  }
}
```

**Rules**:
- Strict TypeScript — no `any` types unless absolutely necessary
- Components follow single responsibility principle
- API calls through dedicated `src/lib/api.ts` layer with React Query
- State management via Zustand stores (keep stores small and focused)
- All UI components use the design system tokens
- Pages compose features, features compose components
- Error boundaries around feature boundaries

### General Rules

- No giant files (>300 lines should be split)
- Meaningful variable/function names
- Docstrings on all service classes and complex functions
- Comments explain "why", not "what"
- TODO markers must include context: `# TODO(username): description - ticket/issue ref`

---

## No-Shortcuts Policy

| Rule | Consequence of Violation |
|------|--------------------------|
| Do NOT skip error handling | Silent failures, poor user experience |
| Do NOT use `# type: ignore` without comment | Hides real type errors |
| Do NOT commit commented-out code | Clutters codebase |
| Do NOT use `any` in TypeScript | Breaks type safety |
| Do NOT bypass service layer | Untestable, coupled code |
| Do NOT hardcode secrets or config | Security vulnerability |
| Do NOT skip input validation | Injection attacks, crashes |
| Do NOT fabricate knowledge in agents | Hallucinated IT advice to users |

---

## Testing Expectations

| Area | Framework | Coverage Target |
|------|-----------|----------------|
| Backend services | pytest (async) | 80%+ |
| Workflow nodes | pytest + mocked LLM | 100% of happy path |
| Frontend components | Vitest + RTL | Key interactions |
| API integration | pytest + httpx | Critical flows |

```bash
# Run tests
make test-backend       # Backend unit + integration
make test-frontend      # Frontend unit
make test-e2e           # Playwright E2E (needs backend running + seeded)
make test               # Everything
make lint               # Linting (both)
```

### Code-quality hooks (enabled via `make install-hooks`)
- **Post-edit (Claude Code)**: `.claude/settings.json` runs `scripts/claude-lint-file.sh` on each edited file — ESLint for frontend `.ts/.tsx`, Ruff for backend `.py`. Lint failures are surfaced back; fix them in the same turn rather than ignoring.
- **Pre-push (git)**: `.githooks/pre-push` gates pushes on frontend lint+typecheck+vitest and backend ruff+mypy+pytest (backend via `uv`). Bypass only with `git push --no-verify` / `SKIP_PREPUSH=1` when intentional.
- Frontend `lint` runs with `--max-warnings=0` — warnings fail. ESLint config: `frontend/.eslintrc.cjs`.

---

## Documentation Expectations

- Every new feature needs a doc update
- Agent changes require updating the corresponding `agents/*.md` file
- API changes require updating OpenAPI schemas (auto-generated from Pydantic)
- Workflow changes require updating `docs/architecture/workflows.md`
- New skills require a new `skills/**/*.md` file

---

## How to Safely Modify Code

1. **Read context first** — Check `agents/*.md` and `skills/**/*.md` for the area you're changing
2. **Check existing tests** — Understand expected behavior before modifying
3. **Make changes incrementally** — Small, focused commits with clear messages
4. **Run validation** — `make lint` and `make test` before considering work done
5. **Update docs** — If you changed architecture, update the relevant `.md` file
6. **Verify workflow** — If modifying the graph, trace the full path manually

---

## Implementation Status

> Last validated: 2026-06-19 — see `plans/phase1-hardening.md` for the full iteration log.

### ✅ Fully Implemented
| Area | Status | Notes |
|------|--------|-------|
| FastAPI backend | ✅ | All routes, CORS, lifespan + background scheduler |
| JWT Auth (local) | ✅ | Login, register, /me, logout, **/auth/refresh**, typed 401 error codes |
| RBAC (5 roles) | ✅ | `require_roles`, `require_permissions`, **typed specialist-chat + KB-promote permissions** |
| Ticket lifecycle | ✅ | SLA, assignment, events, isolation |
| LangGraph workflow | ✅ | 6 nodes + **supervisor shadow node** (Phase-1 dual-run mode) |
| Conversational intent classifier | ✅ | Hybrid LLM-first + keyword safety net; 11 typed intents; versioned |
| Multi-agent registry + supervisor | ✅ | Declarative AGENT_REGISTRY, 7 specialists, pure-function routing decisions, guardrails (handoff cap, loop detection, confidence floor) |
| Specialist agents (7) | ✅ | Outlook + Access/MFA + Zoom/Meetings + Intune + Sixth Sense + Hardware + Network/VPN. Shared `_progression` helper. |
| Knowledge retrieval | ✅ | Grounded published-only retrieval + citations; subtype-aware reranking; **hybrid vector+keyword ranking (Phase 6) behind `FEATURE_VECTOR_RETRIEVAL`** |
| Knowledge Management | ✅ | Structured articles, lifecycle/governance, versioning, taxonomy, indexing, analytics |
| Knowledge Improvement Loop | ✅ | `KnowledgeCandidate` model + service; review-gated promotion; six signal sources |
| Controlled web fallback | ✅ | `ControlledWebResearchAgent`: registry opt-in, trust-tier filter, mandatory candidate creation, audit log |
| Agent tool calling (Phase 5) | ✅ behind flag | Typed `TOOL_REGISTRY` + `AgentToolRuntime` (allow-list, RBAC, approval gate, audit w/ arg+result hashes, bounded loop); 3 local read-only tools; `LLMService.complete_with_tools`; Outlook wired behind `FEATURE_AGENT_TOOLS` (default off). Docs: `docs/architecture/agent-tooling.md` |
| MCP integrations (Phase 7) | ✅ behind flag | Agents consume external systems (Graph: Entra/Intune/Exchange; ServiceNow) as governed MCP-backed read tools behind `FEATURE_MCP_TOOLS` (per-server, default off). Declarative `MCP_SERVER_REGISTRY`, typed tools, typed `integration:*` perms, timeout+degrade. Docs: `docs/architecture/mcp-integrations.md` |
| Gated write actions + background agents (Phase 8) | ✅ behind flag | Human-approved write tools (unlock account, reset MFA, create incident) behind `FEATURE_AGENT_WRITE_ACTIONS`; propose→approve→execute via `AgentToolRuntime` (0 unapproved executions). Async `AgentTaskRunner` for autonomous agents behind `FEATURE_BACKGROUND_AGENTS`. Docs: `docs/architecture/agent-write-actions-and-tasks.md` |
| LLM integration | ✅ | LiteLLM abstraction, hybrid intent path, structural-validity guard on LLM picks, **tool-calling (`complete_with_tools`)** |
| Remote support | ✅ | End-to-end: consent-gated lifecycle, **live-chat bridge** (`POST /specialist-chat/{id}/remote-session`, chat→ticket→session audit chain), employee `ConsentWatcher` + `GET /remote-support/consent/pending`, session sweeper (consent expiry + max duration), provider prereq gate, real Graph-backed Remote Help adapter behind `REMOTE_SUPPORT_USE_MOCK` (dev mock default). ADR: `docs/architecture/remote-support-decision.md` |
| Production hardening (2026-07) | ✅ | `Settings.validate_production()` fail-fast boot; token denylist + refresh rotation; real rate limiting; security-headers + request-metrics middleware; Prometheus `/api/v1/health/metrics`; real readiness probe (DB+Redis, 503); prod-compose `migrate` service; **alembic.ini `version_locations` fix** (upgrade head silently applied nothing before); GHCR release workflow; runbooks `docs/deployment/`. Plan: `plans/production-readiness-2026-07.md` |
| Live IT Specialist Chat | ✅ | Dedicated tables, lifecycle state machine, **7-min idle warning + 2-min grace** (configurable), typed end reasons, full transcript persistence, **typing indicators both ways**, same-window handoff + waiting state, specialist sound/desktop notification |
| Specialist Queue + My Assigned | ✅ | Atomic claim (DB-level), typed HandoffPackage v1.0, REST API, **frontend UI** wired and verified |
| Background scheduler | ✅ | Pure-asyncio loop in FastAPI lifespan; idle sweeper every 30 s |
| Analytics API | ✅ | Dashboard metrics, SLA, workload |
| Audit logging | ✅ | AuditEvent model + service; every specialist-chat transition audited |
| Session expiry handling | ✅ | Typed 401 error codes, single API interceptor, refresh-once mutex, proactive idle-tab logout, centralized redirect, `next=` open-redirect guard |
| Frontend routing | ✅ | Role-aware routes, guards |
| Frontend auth store | ✅ | Zustand persist, **refresh_token + tokenExpiresAt persistence**, idle-tab timer, session-expired event listener |
| Frontend specialist UX | ✅ | `LiveQueuePage`, `AssignedTicketsPage`, `LiveChatPage` — all polling-based, tsc + eslint clean |
| Docker compose | ✅ | Dev + prod targets, health checks |
| Alembic migrations | ✅ | 002…**009** (007=knowledge_candidates, 008=specialist_chat, 009=chat_escalation_artifacts) |
| Chat-escalation artifacts | ✅ | Immutable transcript snapshot + structured escalation context created at escalation; summary-first specialist handoff view; KB gap tags; resolution-comparison fields. `app/models/escalation.py`, `app/services/escalation_service.py`. Docs: `docs/architecture/chat-escalation-artifacts.md` |

### 🚧 Stubbed / Scaffolded (Not Yet Functional)
| Area | Status | Notes |
|------|--------|-------|
| SAML SSO | 🚧 Stub | Endpoints exist; IdP call is `pass` |
| pgvector semantic search | ✅ behind flag | Phase 6: hybrid vector+keyword retrieval wired behind `FEATURE_VECTOR_RETRIEVAL` (default off). `AzureOpenAIEmbeddingClient` + pgvector `cosine_distance`; needs an embedding provider configured + `scripts/backfill_embeddings.py` run. Falls back to keyword otherwise. Docs: `docs/architecture/retrieval-and-indexing.md` |
| WebSocket chat | ❌ Phase 2 | HTTP polling currently; API shape supports drop-in upgrade |
| Knowledge Candidate review UI | ❌ Phase 2 | Backend model + service ready; SME UI deferred |
| Refresh-token rotation + denylist | ✅ Shipped 2026-07 | Rotation on every refresh; old jti revoked via Redis denylist (`app/core/token_store.py`); refresh tokens can't authenticate APIs. Reuse *detection* (family revocation on replay) still deferred |
| Cross-tab BroadcastChannel logout | ❌ Phase 2 | Each tab runs its own idle timer |
| Human Support Copilot | ❌ Future | Spec in agents/08-copilot.md |
| Token blacklisting | ✅ Shipped 2026-07 | Redis jti denylist; logout revokes access (+ refresh when sent); fail-open default, `TOKEN_DENYLIST_FAIL_CLOSED` knob |
| Rate limiting | ✅ Shipped 2026-07 | Real middleware (`app/core/rate_limit.py`): Redis sliding window + local fallback, tighter auth bucket (`RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE`), health/metrics exempt |

### 🔑 Seeded Dev Users (see `scripts/seed_enterprise.py`)
| Email | Password | Role |
|-------|----------|------|
| `employee@aditi.com` | `employee123` | employee |
| `agent@aditi.com` | `agent123` | it_agent |
| `lead@aditi.com` | `lead123` | it_lead |
| `admin@aditi.com` | `admin123` | it_admin |
| `auditor@aditi.com` | `auditor123` | security_auditor |

---
| Pydantic schemas | `backend/app/schemas/` |
| Service layer | `backend/app/services/` |
| Repository layer | `backend/app/repositories/` |
| LangGraph workflow | `backend/app/workflows/` |
| Workflow nodes | `backend/app/workflows/nodes/` |
| Workflow state | `backend/app/workflows/state.py` |
| Workflow graph | `backend/app/workflows/graph.py` |
| LLM abstraction | `backend/app/services/llm_service.py` |
| Knowledge base seed | `backend/app/knowledge_base/seed/` |
| Frontend pages | `frontend/src/pages/` |
| Frontend components | `frontend/src/components/` |
| API client | `frontend/src/lib/api.ts` |
| State stores | `frontend/src/store/` |
| Type definitions | `frontend/src/types/` |

---

## Agent Workflow Overview

```
User Message
    │
    ▼
┌─────────────┐
│ Orchestrator │ ← Deterministic routing (no LLM)
└──────┬──────┘
       │
       ▼
┌─────────────┐     clarification needed
│   Triage    │ ─────────────────────────→ User
│   Agent     │
└──────┬──────┘
       │ classified
       ▼
┌─────────────┐
│ Knowledge   │
│ Retrieval   │
└──────┬──────┘
       │ articles found
       ▼
┌─────────────┐     confidence >= 0.8
│ Resolution  │ ─────────────────────────→ User (with steps)
│   Agent     │
└──────┬──────┘
       │ confidence < 0.8 OR user requests help
       ▼
┌─────────────┐
│ Escalation  │
│   Agent     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Ticketing  │ → Draft ticket/email → User approval
│   Agent     │
└─────────────┘
```

## Confidence Scoring

- Confidence > 0.8: Provide resolution directly
- Confidence 0.5-0.8: Provide resolution with disclaimer, offer escalation
- Confidence < 0.5: Escalate immediately

---

## Environment Setup

### Local Container (Docker Compose) — Recommended

```bash
# 1. Copy and configure environment (required — file is gitignored)
cp .env.example .env
# Edit .env if needed — defaults work for local dev without LLM

# 2. Build images and start all 4 services (postgres, redis, backend, frontend)
docker compose up --build

# Or in detached mode:
docker compose up --build -d

# 3. Seed dev users + knowledge base (first time only)
docker compose exec backend uv run python -m scripts.seed_enterprise

# 4. Verify everything is running
docker compose ps
# Expected: all services STATUS=Up (healthy)
```

**Service URLs once running:**
| Service | URL |
|---------|-----|
| Frontend (React/Vite) | http://localhost:5173 |
| Backend API (FastAPI) | http://localhost:8000 |
| API Docs (Swagger UI) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| Health check | http://localhost:8000/api/v1/health |

**Dev users (seeded by `seed_enterprise.py`):**
| Email | Password | Role |
|-------|----------|------|
| `employee@aditi.com` | `employee123` | employee |
| `agent@aditi.com` | `agent123` | it_agent |
| `lead@aditi.com` | `lead123` | it_lead |
| `admin@aditi.com` | `admin123` | it_admin |
| `auditor@aditi.com` | `auditor123` | security_auditor |

**Key `.env` notes for local container setup:**
- `LLM_API_KEY` can be left empty — the app falls back to keyword-based triage/resolution
- `POSTGRES_HOST`/`REDIS_HOST` in `.env` stay as `localhost`; docker-compose.yml overrides them to `postgres`/`redis` for the backend container
- `RATE_LIMIT_ENABLED=false` is recommended for local dev to avoid hitting limits during testing
- `SECRET_KEY` in `.env` only needs to be cryptographically strong in production

**Stop / clean up:**
```bash
docker compose down          # Stop containers (data volumes preserved)
docker compose down -v       # Stop + delete all data volumes (full reset)
```

### Local Development (no Docker for app)

```bash
# Infrastructure only (Postgres + Redis in Docker)
make dev-infra        # Starts postgres + redis containers

# Then run app locally
make dev-backend      # Backend with uvicorn --reload (requires uv installed)
make dev-frontend     # Frontend with Vite HMR (requires Node 20+)
```

### First-time setup (local, non-Docker)

```bash
cp .env.example .env  # Configure environment
make bootstrap        # Install all deps (uv sync + npm install)
make db-migrate       # Run Alembic migrations
```

### Windows-specific notes
- The `Makefile` uses `/bin/zsh` as shell; on Windows use `docker compose` commands directly or Git Bash/WSL
- Hot-reload source volumes (`./backend/app`, `./frontend/src`) work on Windows with Docker Desktop WSL2 backend enabled

---

## Iterative Development Protocol

When asked to build a new feature or fix a bug:

1. **Clarify scope** — What exactly needs to change? Which agents are affected?
2. **Check existing code** — Read related files before writing new ones
3. **Implement backend first** — Models → Schemas → Services → Routes → Tests
4. **Then frontend** — Types → API → Store → Components → Page
5. **Validate** — Run tests, check types, verify manually
6. **Document** — Update relevant `.md` files

When in doubt, ask rather than assume.
