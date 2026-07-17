# Known Risks — Change Carefully

Areas where a careless edit silently breaks a core guarantee. Before touching any of
these, read the linked docs, run the named eval/tests, and update memory + docs.

## 1. Grounded retrieval (no hallucinated IT advice)
- **Risk**: mixing unrelated KB families back into chat (the classic "inbox full →
  password reset" bug), or letting confidence go high without grounding.
- **Guards**: `agents/subtype_classifier.py`, `grounding.py::ground_results`,
  `confidence.py`. Article `subcategory` must be a real subtype.
- **Verify**: `backend/tests/unit/test_retrieval_eval.py` (hybrid ≥ keyword recall),
  golden conversations. Docs: `docs/architecture/chat-grounding-rules.md`,
  `retrieval-guardrails.md`.

## 2. Escalation & ticket persistence
- **Risk**: creating a ticket without explicit confirmation, non-idempotent tickets,
  or letting a user reach a human before a usable problem statement exists.
- **Guards**: `escalation_policy.py::handoff_context_sufficient` (single gate, two
  call sites), `ChatService._handle_ticketing` / `request_live_agent`. Persistence is
  service-layer only; `ticketing.py` node builds a draft, never persists.
- Docs: `docs/architecture/escalation-and-live-agent-handoff.md`, `chat-to-live-handoff.md`.

## 3. Escalation artifact immutability
- **Risk**: adding an update path to `TranscriptSnapshot`, or mixing post-escalation
  human↔human messages into the snapshot, or dumping raw chat into ticket description.
- **Guards**: `EscalationService` has no snapshot update path; `extract_transcript()`
  returns a copy. Keep human↔human in `specialist_chat_messages`.
- Docs: `docs/architecture/chat-escalation-artifacts.md`, `transcript-snapshot-and-context-model.md`.

## 4. RBAC & data isolation
- **Risk**: employees seeing others' data, internal notes, drafts, or debug traces;
  UI/backend permission drift; stripping a user's last role.
- **Guards**: `require_roles` / `require_permissions` in services (not routes);
  `frontend/src/lib/permissions.ts` must mirror `core/permissions.py`; admin service
  keeps ≥1 role. Backend always re-checks — UI gating is not security.
- Docs: `docs/security/rbac-matrix.md`, `access-control.md`.

## 5. Gated write actions (Phase 8)
- **Risk**: executing a human-gated tool without an approval token, or approval
  bypassing RBAC.
- **Guards**: `AgentToolRuntime` execution gate is **always on** regardless of feature
  flag; `execute_approved` re-dispatches through the full gate. Eval asserts
  **0 unapproved executions** and RBAC-no-bypass.
- **Verify**: `test_action_safety_eval.py`. Docs: `agent-write-actions-and-tasks.md`.

## 6. Tool / MCP allow-lists
- **Risk**: making a tool callable that isn't declared, or exceeding a server's
  `side_effect_ceiling`.
- **Guards**: enumerated `TOOL_REGISTRY` / `MCP_SERVER_REGISTRY` (versioned);
  `AgentToolRuntime.dispatch` allow-list → existence → args → RBAC → approval → execute,
  audited on every path (incl. rejections).
- **Verify**: `test_tool_routing_eval.py`, `test_mcp_contract_eval.py` (0-unauthorized).

## 7. Migrations & pgvector
- **Risk**: an edit that assumes vectors exist when a chunk is `pending`; a migration
  that isn't reversible; schema change without bumping contracts.
- **Guards**: indexing marks `indexed` only with a real vector; hybrid ranking has a
  keyword floor and degrades safely. Every migration needs a tested downgrade.
- Docs: `retrieval-and-indexing.md`. Skill: `skills/playbooks/database-migrations.md`.

## 8. Config contract stability
- `ExtractionCandidate` (`SCHEMA_VERSION`), `HandoffPackage`, registry `*_VERSION`
  values, ranking weights (must sum to 1.0). Bump the version when changing a contract;
  never silently reshape a typed output.

## 9. No dummy data in product flows
- Analytics rates that can't be computed render "No data", never `NaN%`. No placeholder
  cards, seeded fake tickets, or mock responses in employee/specialist/admin runtime
  paths. Mocks belong in tests and `mcp/mock_session.py` (dev-only, `MCP_USE_MOCK`).

## 10. Frontend session/auth flow
- **Risk**: breaking the refresh-once mutex, idle-tab logout, or open-redirect guard.
- Docs: `docs/architecture/session-expiry.md`.

## 11. Scheduled-report replica-safe claim (C2)
- **Risk**: the monthly report email double-sends across replicas. The guarantee is
  "exactly one successful send per month" via the `scheduled_report_runs` unique
  `period` claim.
- **Guards**: `ScheduledReportService._claim_period` commits the `sending` claim
  (SELECT ... FOR UPDATE on reuse; unique-insert race → IntegrityError → skip)
  **before** `sender.send()` — never defer the claim past the send. `sent` is
  terminal (never resend); `sending` is not auto-resumed; `failed` is reclaimable.
  `should_send` is a catch-up window (`day >= SCHEDULED_REPORT_DAY`) so a missed
  send-day still delivers once (claim prevents duplicates).
- **Verify**: `test_scheduled_report_service.py` (esp. the claim-before-send
  ordering + already-sent-skip tests). Behind `FEATURE_SCHEDULED_REPORTS`.
