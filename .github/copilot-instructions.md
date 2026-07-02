# Copilot Instructions for Aditi IT Assist

> **Repo-wide rules below.** Path-scoped rules also apply automatically via
> `.github/instructions/*.instructions.md` (backend, frontend, tests, ai-workflows,
> admin-console, migrations, docs). For deeper context, prefer real integrations over
> mock/demo code and consult `memory/` (project overview, architecture, domain model,
> known risks), the process in `docs/development/engineering-workflow.md`, and task
> playbooks in `skills/playbooks/`. Framework index: `docs/development/ai-development-framework.md`.
> Use the Makefile commands (`make lint`, `make typecheck`, `make test`) — never invent build steps.

## Project Context

This is **Aditi IT Assist** — an enterprise-grade internal IT service platform for
Aditi Consulting. It uses a multi-agent LangGraph workflow to resolve employee
IT issues through a conversational interface, with full RBAC, ticketing lifecycle,
remote assistance orchestration, analytics, and future SAML SSO integration.

## Architecture

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / LangGraph
- **Frontend**: React / TypeScript / Vite / Tailwind CSS / shadcn/ui
- **AI**: LangGraph orchestration with LiteLLM provider abstraction
- **Auth**: Pluggable provider (local + SAML stub) with JWT sessions
- **RBAC**: Role-based (employee, it_agent, it_lead, it_admin, security_auditor)
- **Vector Search**: pgvector for knowledge retrieval

## Enterprise Patterns

### Auth & RBAC
- Auth providers in `backend/app/services/auth/providers/`
- Use `CurrentUser`, `ITAgentUser`, `ITLeadUser`, `AdminUser` type aliases
- `require_roles()` and `require_permissions()` for endpoint guards
- Employees can ONLY see their own data (tickets, chats)
- Internal notes are hidden from employees

### Services
- `AuthService` — login, registration, token validation
- `TicketService` — full ticket lifecycle with SLA
- `RemoteSupportService` — remote assist orchestration
- `AnalyticsService` — dashboard metrics
- `AuditService` — immutable event logging

### Frontend Structure
- `/support/*` — Employee workspace (chat, tickets, profile)
- `/operations/*` — IT agent workspace (queue, tickets, remote assist)
- `/dashboard/*` — Admin/lead workspace (analytics, management)
- `/audit` — Audit log viewer (admin + auditor)

## Coding Conventions

### Python
- Use type hints everywhere
- Async functions for I/O operations
- Pydantic v2 for all schemas
- Service layer pattern (routes → services → repositories)
- structlog for logging
- 100 char line length
- Ruff for linting and formatting

### TypeScript
- Strict TypeScript (no `any`)
- Functional components with hooks
- React Query for server state
- Zustand for client state
- Tailwind CSS utility classes
- Component-per-file pattern

### General
- Small, focused files (< 300 lines)
- Meaningful names over comments
- Tests for all service methods
- Error handling is mandatory
- No hardcoded configuration values

## File Organization

When creating new features:
1. Backend: model → schema → repository → service → route
2. Frontend: types → api → store → components → page
3. Tests alongside implementation

## Key Patterns

### API Endpoints
```python
@router.post("/resource", response_model=ResourceResponse)
async def create_resource(
    data: ResourceCreate,
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    return await service.create(data)
```

### React Components
```typescript
interface Props {
  title: string;
  onAction: () => void;
}

export function Component({ title, onAction }: Props) {
  return (/* JSX */);
}
```

### LangGraph Nodes
```python
async def node_name(state: WorkflowState) -> WorkflowState:
    # Process state
    # Return updated state
    return {**state, "field": new_value}
```

## What NOT to Do
- Don't bypass the service layer
- Don't use `any` in TypeScript
- Don't skip error handling
- Don't hardcode secrets
- Don't create files > 300 lines
- Don't skip tests for services

## Knowledge Management
- Structured, governed articles — not a CRUD page. Lifecycle:
  `draft → in_review → approved → published → archived`.
- The chat agent retrieves **published articles only** (`KnowledgeRetrievalService`);
  never expose drafts to employee chat.
- Three boundaries: management (`services/knowledge/management.py`), retrieval
  (`retrieval.py`), indexing (`indexing.py`). The workflow consumes retrieval only.
- Lifecycle/validation rules are pure functions in `services/knowledge/lifecycle.py`.
- Authorize with `require_permissions(knowledge:*)`; the transition endpoint enforces
  the specific per-action permission inside the service.
- Data-access goes through `repositories/knowledge_repository.py` (no inline queries).
- Frontend: gate UI with `lib/permissions.ts` (`hasPermission`), data via React Query
  hooks in `features/knowledge/api.ts`. Backend always re-checks.
- Docs: `docs/architecture/knowledge-management.md` and siblings.

## Document Ingestion Pipeline
- **Core principle**: "Schema-stable, parser-flexible." `ExtractionCandidate`
  in `services/ingestion/schema.py` is the stable output contract — never change
  it without bumping `SCHEMA_VERSION`.
- **Adding new document formats**: create a `ParserProfile` in
  `services/ingestion/profiles/` and register it. NO code changes to the
  extraction engine are needed. See `docs/development/parser-rules.md`.
- **Five service layers** (each independent):
  - `extractor.py` — raw text only
  - `normalizer.py` — structure tokens only, no semantic decisions
  - `segmenter.py` — topic segments + `section_map`, no field values
  - `field_extractor.py` — deterministic field values, no LLM
  - `llm_extractor.py` — additive LLM enrichment with hallucination guard
- **Confidence**: every `FieldExtraction` carries `confidence`, `method`,
  `source_excerpt`. Composite score uses profile weights. `review_required = True`
  when `confidence_level` is LOW or VERY_LOW.
- **Pipeline must NEVER auto-publish** — all candidates require human review.
- **LLM enrichment** (`INGESTION_LLM_ENABLED`): opt-in, only fills fields below
  `profile.thresholds.medium`. Hallucination guard discards values not grounded
  in source text.
- Docs: `docs/architecture/document-ingestion.md`,
  `docs/architecture/knowledge-ingestion-pipeline.md`,
  `docs/development/parser-rules.md`,
  `docs/development/extraction-schema.md`.

## Post-Chat Feedback System
- **Data model**: `conversation_feedback` (one per session per user, idempotent
  upsert) + `message_feedback` (thumbs up/down per message). Both in
  `models/feedback.py`, exported from `models/__init__.py`.
- **`quality_bucket`** (POSITIVE/NEUTRAL/NEGATIVE) and **`review_flag`** are
  computed at write time in `feedback_service.py` — never re-derive them in
  queries.
- **Service boundaries**: `feedback_service.py` handles submission/idempotency;
  `feedback_analytics_service.py` handles aggregations; `repositories/feedback_repository.py`
  owns all DB access.
- **Knowledge improvement loop**: `FeedbackAnalyticsService.flag_articles_for_review()`
  identifies articles with ≥3 negative sessions. Caller writes flag to KB — this
  service is read-only with respect to the KB.
- **No auto-publish/unpublish of KB articles** from feedback signals.
- **Privacy**: employees may only submit feedback for their own sessions.
  Comment text gated to `it_agent+`. No survey spam (one per session).
- **Permissions**: `feedback:submit` → employee+; `feedback:view_analytics`
  and `feedback:review` → it_lead, it_admin. Defined in `core/permissions.py`.
- **Frontend**: `PostChatFeedbackCard.tsx` (5-step wizard), `MessageFeedbackControls.tsx`
  (inline thumbs), `feedbackApi.ts` (React Query hooks), all in `features/chat/`.
  Admin queue: `pages/admin/FeedbackReviewPage.tsx`, route `/dashboard/feedback/review`.
- Docs: `docs/product/feedback-workflow.md`, `docs/architecture/feedback-analytics.md`,
  `docs/architecture/conversation-feedback-model.md`,
  `docs/architecture/knowledge-feedback-loop.md`,
  `docs/security/feedback-access-and-privacy.md`.

## Conversational Intelligence (Entity + Intent + Playbooks)
- **Entity normalization**: `services/agents/entity_normalizer.py` maps fuzzy
  product/system mentions (including typos) to canonical system IDs.
  Uses three-phase matching: exact alias → substring → fuzzy (SequenceMatcher).
- **Intent detection**: `detect_issue_intent()` extracts login, lock, OTP,
  error, crash, performance flags from user text. Orthogonal to entity.
- **Playbook registry**: `services/agents/playbooks.py` — each supported system
  has a diagnostic playbook that defines required slots, clarification questions,
  retrieval filters, and escalation triggers.
- **Triage flow**: entity normalize → intent detect → classify → playbook
  evaluate → clarify or proceed. Entity match overrides broad keyword categories.
- **Entity-specific playbooks**: `SIXTH_SENSE_PLAYBOOK`, `OUTLOOK_PLAYBOOK`,
  `ZOOM_PLAYBOOK`, etc. Use `get_playbook_for_entity(canonical_name)`.
- **Context persistence**: `DiagnosticContext` carries `normalized_system`,
  `login_issue_flag`, `blocked_account_flag`, `otp_issue_flag` across turns.
  Chat service no longer resets context between non-clarification turns.
- **Escalation policy**: only escalate after meaningful diagnostic attempt —
  never on first symptom mention. Include entity context in handoff summary.
- **No-direct-connect**: a user cannot reach a live specialist (or create the
  ticket) before a minimally-useful problem statement exists. Shared gate
  `app/services/agents/escalation_policy.py::handoff_context_sufficient`, fired
  in triage (`_gather_problem_before_handoff`) and `ChatService.request_live_agent`.
- **Live specialist chat**: same-window handoff with a "please wait" state;
  typing indicators both ways (`POST /specialist-chat/{id}/typing`, ephemeral
  in-memory, no idle reset); idle = 7-min warning + 2-min grace → auto-end;
  specialist queue plays a chime + desktop notification on new handoffs
  (`frontend/src/lib/notification-sound.ts`).
- **Chat-escalation artifacts**: on escalation, two linked **immutable** records
  are created (`app/models/escalation.py`): a `TranscriptSnapshot` (write-once
  Employee↔AI history) + an `EscalationContext` (one per ticket; attempted steps,
  `kb_gap_tags`, escalation reason, routing, resolution-comparison fields).
  Created in `ChatService._persist_and_queue`; served via
  `EscalationService.get_handoff_view` and `GET /specialist-queue/{id}/handoff-view`
  (summary-first, transcript-second; rendered by
  `features/specialist-chat/HandoffContextPanel.tsx`). Never shove raw chat into
  the ticket description; link to the artifacts. Improvement is human-reviewed
  only — no self-learning. Migration `009_chat_escalation_artifacts`.
- Escalation-artifact docs: `docs/architecture/chat-escalation-artifacts.md`,
  `docs/architecture/transcript-snapshot-and-context-model.md`,
  `docs/product/chat-to-ticket-handoff.md`,
  `docs/product/specialist-triage-experience.md`,
  `docs/development/chat-escalation-qa-checklist.md`.
- Live-chat docs: `docs/architecture/chat-to-live-handoff.md`,
  `docs/architecture/live-chat-session-lifecycle.md`,
  `docs/architecture/idle-timeout-and-typing-indicators.md`,
  `docs/product/chat-and-live-support-flow.md`,
  `docs/development/live-chat-qa-checklist.md`.
- Docs: `docs/architecture/intent-analysis.md`,
  `docs/architecture/entity-normalization.md`,
  `docs/architecture/chat-playbooks.md`,
  `docs/product/conversation-quality-guidelines.md`,
  `docs/development/failure-cases-and-golden-conversations.md`.

## Admin Console

The Admin Console (it_lead / it_admin; auditor for audit) is admin-focused — no
cross-workspace "profile switch". Sections: Analytics, Team Queue, Knowledge Base,
User Management, Audit Logs.

- Backend: `app/api/v1/admin.py` → `app/services/admin/` (user mgmt, audit query,
  stats) + `app/schemas/admin.py`. Gate with `require_permissions` (`admin:manage_users`,
  `admin:assign_roles`, `admin:view_audit_log`). Audit-log every user/role mutation
  with before/after diffs; never strip a user's last role.
- Frontend: `src/features/admin/` (typed React Query hooks, `utils.ts`, `components/badges.tsx`)
  and `src/components/admin/` (`Breadcrumbs`, `PageHeader`). Put pure helpers in
  non-component files (react-refresh lint rule). Add breadcrumbs to every deep page.
- Real data only — no dummy cards. Rates that can't be computed render "No data",
  not `NaN%`. Keep `src/lib/permissions.ts` in sync with the backend registry.
- Docs: `docs/product/admin-console.md`, `docs/architecture/admin-console-architecture.md`,
  `docs/development/admin-qa-checklist.md`.
