# Glossary

Business and system terms used across Aditi IT Assist.

## Roles
- **Employee** — end user submitting IT issues; sees only their own data.
- **IT Agent / Specialist** (`it_agent`) — resolves escalated issues via queue + live chat.
- **IT Lead** (`it_lead`) — agent powers + assignment, approvals, analytics.
- **IT Admin** (`it_admin`) — user/role/KB governance, admin console.
- **Security Auditor** (`security_auditor`) — read-only audit/compliance access.

## Chat & AI
- **Triage** — classifying an incoming issue (category + subtype) before retrieval.
- **Subtype** — fine-grained issue class (e.g. `mailbox-full`); set deterministically by
  `subtype_classifier`; a KB article's `subcategory` must equal a real subtype.
- **Grounding** — enforcing that only relevant, published KB is used; cross-family
  matches are rejected (`grounding.py`).
- **DiagnosticContext** — per-session state (subtype, normalized system, intent flags,
  tried/failed steps) persisted across turns.
- **Playbook** — per-system diagnostic script (required slots, clarifications,
  retrieval filters, escalation triggers).
- **Composite confidence** — score that can't be high without grounding; penalized for
  loops/unresolved state.
- **Supervisor (shadow) node** — routing decision-maker that runs in dual-run mode.
- **Entity normalization** — mapping fuzzy product mentions/typos to canonical system IDs.

## Handoff & tickets
- **Escalation** — moving from AI to human when grounded help is exhausted or requested.
- **Handoff context sufficient** — the gate requiring a minimally-useful problem
  statement before any human handoff / ticket creation.
- **HandoffPackage** — typed payload a specialist receives when claiming a ticket.
- **Transcript snapshot** — write-once Employee↔AI history captured at escalation.
- **Escalation context** — structured, one-per-ticket handoff record.
- **KB gap tag** — controlled-vocabulary tag marking why the KB didn't resolve an issue
  (e.g. `no_matching_article`, `missing_runbook`); feeds human-reviewed KB improvement.
- **Idle warning / grace** — 7-min inactivity warning + 2-min grace before auto-end of live chat.

## Knowledge
- **Lifecycle** — `draft → in_review → approved → published → archived`.
- **Published-only retrieval** — chat may only surface published articles.
- **KnowledgeCandidate** — proposed KB change awaiting SME review (never auto-published).
- **Indexing / backfill** — creating pgvector embeddings; `pending` until a real vector exists.
- **Hybrid retrieval** — vector + keyword + usage + quality blend (behind flag), with a
  keyword floor so it never scores below keyword-only.

## Platform / governance
- **RBAC** — role-based access control; `require_roles` / `require_permissions`.
- **Audit event** — immutable log of a mutation with before/after diff.
- **Feature flag** — `FEATURE_*` env toggle; all default off in code.
- **AgentToolRuntime** — single enforcement point for tool calls (allow-list → RBAC →
  approval → execute, all audited).
- **MCP** — Model Context Protocol; external systems (MS Graph, ServiceNow) surfaced as
  governed tools.
- **Propose → approve → execute** — the human-in-the-loop path for write actions.
- **Eval dataset** — YAML fixtures under `backend/tests/data/` that gate agent behavior.

## Stack shorthands
- **uv** — Python package/deps manager (backend). **Ruff** — py lint/format.
- **LiteLLM** — provider-agnostic LLM abstraction. **LangGraph** — workflow orchestration.
- **pgvector** — Postgres vector extension. **React Query / Zustand** — server / client state.
