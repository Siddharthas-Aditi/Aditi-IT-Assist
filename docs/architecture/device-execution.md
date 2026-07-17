# Autonomous Device Execution — mechanics (Phase 9)

Decision + rationale: `docs/architecture/device-execution-decision.md`. This doc
is the implementation reference.

## What it does

Lets an agent act on an Intune-managed endpoint through three catalog-bound,
policy-gated tools, governed by the same `AgentToolRuntime` as every other tool:

| Tool | Effect | Catalog |
|------|--------|---------|
| `install_win32_app` | Install an approved app (Python, Docker Desktop, VS Code, Node) | `APP_CATALOG` |
| `run_remediation_script` | Run an approved remediation (clear Teams cache, flush DNS, …) | `REMEDIATION_CATALOG` |
| `device_action` | Benign built-in action (sync, restart) | `DEVICE_ACTION_CATALOG` |

The agent supplies a **catalog id + device id + idempotency key** (and optional
justification). It never supplies an installer, a script body, or a command.

## Request flow (end-to-end)

```
caller (agent turn or POST /device-execution/actions)
      │
      ▼
DeviceExecutionService.request_action
      │  1. validate tool + args
      │  2. DeviceGuardrails.facts → Intune eligibility (MCP read) + consent (RemoteSupportConsent)
      │  3. evaluate_device_action(...)  → autonomous | human_approval | deny
      ▼
   decision
   ├─ deny            → denied outcome (nothing dispatched or queued)
   ├─ human_approval  → ApprovalQueue.propose(...) → parked in /agent-ops/approvals
   │                     (it_lead approves → re-check consent → execute_approved)
   └─ autonomous      → mint scoped token → AgentToolRuntime.dispatch
                         │  allow-list → arg schema → RBAC(integration:device_execute)
                         │  → approval gate (token present) → audit
                         ▼
                       DeviceExecutionTool.run  (defense in depth)
                         │  resolve catalog entry (off-catalog ⇒ denied, no call)
                         │  re-evaluate policy (risk / injection / eligibility)
                         ▼
                       call msgraph_intune_exec MCP tool with the catalog's
                       published Intune id → status=executed
```

The tool spec is ``approval=human``: the runtime **never** executes a device tool
without a token. Only ``DeviceExecutionService`` mints an *autonomous* token, and
only after the policy clears the action; everything else is queued or denied.

## Modules

| Concern | File | Version const |
|---------|------|---------------|
| Catalog (allow-list of runnable actions) | `app/services/agents/device_actions/catalog.py` | `CATALOG_VERSION` |
| Autonomy policy (pure decision fn + injection scan) | `.../device_actions/policy.py` | `AUTONOMY_POLICY_VERSION` |
| Guardrails (Intune eligibility + consent) | `.../device_actions/guardrails.py` | — |
| Execution tools + builder | `.../device_actions/tools.py` | — |
| Orchestrator (route: auto/queue/deny + approve) | `.../device_actions/service.py` | — |
| Exec MCP server profile | `.../mcp/profiles.py` (`msgraph_intune_exec`) | `MCP_PROFILE_VERSION` |
| Mock responses | `.../mcp/mock_session.py` | — |
| Permission | `app/core/permissions.py` (`integration:device_execute`) | — |
| Approval queue (shared) | `.../agents/approvals.py` (includes device tools) | — |
| API + schemas | `app/api/v1/device_execution.py`, `app/schemas/device_execution.py` | — |
| Runtime merge | `.../tools/registry.py` (`build_default_runtime(include_device_execution=True)`) | `TOOL_REGISTRY_VERSION` |
| Specialist allow-list | `.../registry.py` (`device_intune`) | `REGISTRY_VERSION` |

## API

| Endpoint | Role | Purpose |
|----------|------|---------|
| `GET /device-execution/catalog` | it_agent+ | What may run + current autonomy config |
| `POST /device-execution/actions` | it_agent+ | Request an action → executed / pending_approval / denied |
| `POST /device-execution/approvals/{id}/approve` | it_lead+ | Carry out a parked action (re-checks consent + eligibility) |
| `POST /device-execution/approvals/{id}/reject` | it_lead+ | Reject a parked action |

Parked device actions also appear in the shared `GET /agent-ops/approvals` queue.

## Consent model

Device execution reuses the remote-support consent artifact (`RemoteSupportConsent`):
an active, granted, non-revoked consent for the device's **owner** (the primary user
resolved server-side from the Intune device record — not a caller-supplied name) is
required. Consent is enforced in the **tool layer** (`DeviceExecutionTool.run` via
`DeviceGuardrails.as_tool_provider`), so it is re-checked on *every* execution path:
autonomous, the device-execution approve endpoint, **and** the generic `/agent-ops`
approval queue. The service also checks it at request time. In dev (`MCP_USE_MOCK`)
consent defaults permissive so the flow is exercisable; production uses the DB lookup.

## Frontend

- **Device Actions** page (`/operations/device-actions`, `pages/operations/DeviceActionsPage.tsx`):
  IT staff pick a catalog action, name the device + employee, submit, and see the
  typed outcome (executed / queued / denied) with risk tier + policy signals.
- Feature module `frontend/src/features/device-execution/` (typed API + React Query hooks).
- Queued actions surface in the existing **Approval Queue** page for it_lead to action.

## Guardrails (defense in depth)

1. **Catalog membership** — only ids in the catalog can run; no free-form payload.
2. **Risk tiers** — HIGH never autonomous; MEDIUM only when opted in; LOW autonomous.
3. **Two config gates** — `FEATURE_DEVICE_EXECUTION` (build) and
   `DEVICE_EXECUTION_AUTONOMOUS` (autonomy kill-switch). Prod fail-fast if the
   feature is on with `MCP_USE_MOCK=true`, or autonomy on with the feature off.
4. **RBAC + SSO** — `integration:device_execute` (it_lead+); Entra SSO bounds identity.
5. **Consent + eligibility** — live consent + Intune precheck required (GuardrailProvider).
6. **Injection scanner** — suspicious justification ⇒ human approval (never expands capability).
7. **Audit** — runtime records arg/result hashes on every dispatch; result carries
   decision, risk tier, and policy signals.

## Config

```
FEATURE_DEVICE_EXECUTION=true
DEVICE_EXECUTION_AUTONOMOUS=true          # kill-switch; off ⇒ all actions → human approval
DEVICE_EXECUTION_AUTONOMOUS_MEDIUM=false  # opt medium-risk into autonomy
MCP_ENABLED_SERVERS=["...","msgraph_intune_exec"]
MCP_USE_MOCK=true                         # dev; false in prod with real Graph
```

## Tests / gates

- `tests/unit/test_device_actions.py` — catalog integrity, injection scanner, policy gate.
- `tests/unit/test_device_execution_safety_eval.py` + `tests/data/device_execution_safety_eval.yaml`
  — 0-autonomous-above-threshold, 0-off-catalog-execution, contract pins, dispatch gates.

## Adding a runnable action

1. Publish the Win32 app / remediation script in Intune; note its id.
2. Add one entry to the relevant catalog with a `RiskTier` and `rollback_ref`.
3. Bump `CATALOG_VERSION`. Add an eval case. PR review.
