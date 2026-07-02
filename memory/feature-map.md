# Feature Map

Feature → the code that owns it and the docs that describe it. Use this to jump
straight to the right files instead of grepping blind.

## Employee chat & AI troubleshooting
- Backend: `app/services/agents/chat_service.py`, `app/workflows/` (nodes + graph),
  `agents/subtype_classifier.py`, `grounding.py`, `confidence.py`,
  `resolution_strategy.py`, `playbooks.py`, `entity_normalizer.py`,
  `intent_classifier.py` / `llm_intent.py`. API: `app/api/v1/chat.py`.
- Frontend: `features/chat/` (`ChatBubble.tsx`, feedback controls), `pages/ChatPage.tsx`.
- Docs: `docs/architecture/chat-grounding-rules.md`, `troubleshooting-state-machine.md`,
  `retrieval-guardrails.md`, `multi-turn-chat-design.md`, `chat-playbooks.md`,
  `docs/product/employee-chat-experience.md`, `conversation-quality-guidelines.md`.
- Skill: `skills/playbooks/chat-to-ticket-handoff.md`, `rag-and-knowledge-workflow.md`.

## Ticket creation & triage
- Backend: `app/services/ticket_service.py`, `app/services/agents/chat_service.py`
  (`_handle_ticketing`), workflow `nodes/ticketing.py`. API: `app/api/v1/tickets.py`.
  Models: `ticket.py`, `support.py`.
- Docs: `docs/architecture/ticketing-lifecycle.md`, `escalation-and-live-agent-handoff.md`.

## Live specialist handoff & queue
- Backend: `app/services/specialist_chat_service.py`, `specialist_queue_service.py`,
  `escalation_service.py`. API: `specialist_chat.py`, `specialist_queue.py`.
  Models: `specialist_chat.py`, `escalation.py`.
- Frontend: `features/specialist-chat/` (`HandoffContextPanel.tsx`),
  `pages/operations/` (`LiveQueuePage`, `AssignedTicketsPage`, `LiveChatPage`),
  `lib/notification-sound.ts`.
- Docs: `docs/architecture/chat-to-live-handoff.md`, `live-chat-session-lifecycle.md`,
  `idle-timeout-and-typing-indicators.md`, `human-handoff-and-queue.md`,
  `chat-escalation-artifacts.md`, `transcript-snapshot-and-context-model.md`,
  `docs/product/it-specialist-workflow.md`, `specialist-triage-experience.md`,
  `chat-to-ticket-handoff.md`.
- Skill: `skills/playbooks/specialist-queue-flow.md`, `live-chat-flow.md`.

## Knowledge base & governance
- Backend: `app/services/knowledge/` (management, retrieval, indexing, lifecycle,
  ranking), `knowledge_service.py`, `repositories/knowledge_repository.py`.
  API: `knowledge.py`, `knowledge_admin.py`. Candidates: `knowledge_candidate.py`.
- Frontend: `features/knowledge/`.
- Docs: `docs/architecture/knowledge-management.md`, `retrieval-and-indexing.md`,
  `knowledge-improvement-loop.md`, `docs/product/knowledge-workflow.md`,
  `docs/security/knowledge-access-control.md`.
- Skill: `skills/playbooks/rag-and-knowledge-workflow.md`.

## Document ingestion
- Backend: `app/services/ingestion/` (extractor, normalizer, segmenter,
  field_extractor, llm_extractor, profiles/, schema.py). Model: `ingestion.py`.
  Frontend: `features/ingestion/`.
- Docs: `docs/architecture/document-ingestion.md`, `knowledge-ingestion-pipeline.md`,
  `docs/development/parser-rules.md`, `extraction-schema.md`.

## Agent tools / MCP / write actions / background agents (flagged)
- Backend: `agents/tools/` (registry, runtime), `agents/mcp/` (profiles, session,
  tools, mock_session), `agents/tasks/`, `agents/approvals.py`.
  API: `app/api/v1/agent_ops.py`. Frontend: `features/agent-ops/`.
- Docs: `docs/architecture/agent-tooling.md`, `mcp-integrations.md`,
  `agent-write-actions-and-tasks.md`, `docs/development/agentic-local-testing.md`.
  Roadmap: `plans/agentic-ops-platform-evolution.md`.

## Admin console
- Backend: `app/api/v1/admin.py` → `app/services/admin/` + `app/schemas/admin.py`.
- Frontend: `features/admin/`, `components/admin/`, `pages/admin/`.
- Docs: `docs/product/admin-console.md`, `docs/architecture/admin-console-architecture.md`,
  `docs/development/admin-qa-checklist.md`. Skill: `skills/playbooks/frontend-admin-console.md`.

## Auth, RBAC, sessions
- Backend: `app/services/auth/` (providers/, dependencies.py), `core/permissions.py`,
  `core/security.py`. Model: `auth.py`, `sso.py`. API: `auth.py`.
- Frontend: auth Zustand store, API interceptor (`lib/api.ts`).
- Docs: `docs/architecture/authentication.md`, `access-control.md`, `session-expiry.md`,
  `docs/security/rbac-matrix.md`, `saml-roadmap.md`.

## Feedback & knowledge improvement loop
- Backend: `feedback_service.py`, `feedback_analytics_service.py`,
  `repositories/feedback_repository.py`. Frontend: `features/chat/` feedback pieces,
  `pages/admin/FeedbackReviewPage.tsx`.
- Docs: `docs/product/feedback-workflow.md`, `docs/architecture/feedback-analytics.md`,
  `conversation-feedback-model.md`, `knowledge-feedback-loop.md`.

## Analytics, audit, remote support
- Analytics: `analytics_service.py`, `app/api/v1/analytics.py`, `docs/architecture/analytics.md`.
- Audit: `audit_service.py`, model `audit.py`, `docs/security/consent-and-audit.md`.
  Skill: `skills/playbooks/audit-logging.md`.
- Remote support: `remote_support_service.py`, `docs/architecture/remote-support.md`.

## Eval datasets (guard rails)
`backend/tests/data/`: `tool_routing_eval.yaml`, `retrieval_eval.yaml`,
`mcp_contract_eval.yaml`, `action_safety_eval.yaml`; golden convos in
`docs/development/golden-conversations.md`.
