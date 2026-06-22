# Gated Write Actions & Background Agents (Phase 8)

> The final layer of the agentic platform: agents can take **write actions** in
> external systems (unlock an Entra account, reset MFA, create a ServiceNow
> incident) — every one **human-approved by default** — and can run
> **autonomously in the background** via a governed task runner.
>
> Status: **landed behind two flags, both default off** —
> `FEATURE_AGENT_WRITE_ACTIONS` and `FEATURE_BACKGROUND_AGENTS`. The
> approval-gate and write/destructive machinery were built in Phase 5; Phase 8
> wires the real write tools and the background runner on top.

See also: [`agent-tooling.md`](./agent-tooling.md),
[`mcp-integrations.md`](./mcp-integrations.md),
[`../../plans/agentic-ops-platform-evolution.md`](../../plans/agentic-ops-platform-evolution.md) (Phase 8).

## 1. Gated write actions

### Tools (MCP-backed, write-classified)

| Tool | Server | Side effect | Approval | Permission |
|---|---|---|---|---|
| `entra_unlock_account` | msgraph | write | human | `integration:directory_write` |
| `reset_mfa` | msgraph | write | human | `integration:directory_write` |
| `servicenow_create_incident` | servicenow | write | human | `integration:ticketing_write` |

All three are `WRITE` (never `DESTRUCTIVE` in Phase 8) and take an
`idempotency_key` so a retry of the same intended action de-dupes server-side.
The new write permissions are granted to **`it_lead` and `it_admin`** — a higher
bar than the Phase-7 read permissions (which `it_agent` holds).

### Two independent gates

1. **Build gate** (`FEATURE_AGENT_WRITE_ACTIONS`): `build_mcp_tools` only
   constructs write/destructive tools when this is on. A Phase-7 deployment with
   only `FEATURE_MCP_TOOLS` stays strictly read-only even though the server
   profiles' `side_effect_ceiling` now permits writes.
2. **Execution gate** (always on): the `AgentToolRuntime` returns
   `needs_approval` for any `approval=human` tool unless the caller's context
   carries an explicit approval token for that tool — and **does not execute it**.
   This is independent of the build flag and cannot be turned off.

### Propose → approve → execute

```
agent tool loop ──hits a write tool──▶ ToolOutcome(needs_approval) + ProposedAction
                                              │  (surfaced to the IT specialist queue UI)
                          human approves ──────┤
                                              ▼
   runtime.execute_approved(proposed, approver_ctx, approver_id=…)
       → re-dispatches the EXACT captured invocation under an approval-bearing context
       → full gate re-runs: allow-list, arg validation, RBAC, audit (args+result hash), idempotency
```

Key guarantees (enforced + tested):

- **0 unapproved executions.** Without an approval token the underlying MCP
  server is never called (`test_action_safety_eval.py` asserts the fake server
  records zero calls).
- **Approval ≠ RBAC bypass.** The approver must themselves hold the tool's
  `required_permissions`; an under-privileged approver gets `rejected_forbidden`.
- **What's approved is what runs.** `ProposedAction` captures the exact
  invocation; `execute_approved` re-dispatches it verbatim.
- **Idempotent.** The `idempotency_key` arg lets the server dedupe retries.

The backend contract is complete; the specialist **queue-UI** affordance to
render and approve/reject a `ProposedAction` is the remaining integration
(API + frontend) and is tracked as a follow-up.

## 2. Background / autonomous agents

`app/services/agents/tasks/` is a small, governed task layer that runs agent
work off the request path.

| Module | Responsibility |
|---|---|
| `models.py` | `AgentTask` (typed, storage-agnostic) + `AgentTaskStatus`. |
| `store.py` | `AgentTaskStore` protocol + `InMemoryAgentTaskStore` (lock-guarded, idempotent enqueue, atomic claim). |
| `runner.py` | `AgentTaskRunner`: register handlers per `task_type`, `run_once` (claim + execute with bounded concurrency, retry-then-fail, audit), `run_forever` (poll loop). |
| `handlers.py` | Reference agents: `knowledge_improvement_sweep` (nightly candidate review — never auto-publishes) and `proactive_diagnostics` (pre-fetch read-only MCP diagnostics for a handoff). |
| `factory.py` | `build_default_task_runner()` — composition root; safe no-op default dependencies until real data sources are wired. |

Properties:

- **Bounded concurrency** via a semaphore (`AGENT_BACKGROUND_CONCURRENCY`); a
  single task's failure can never crash the loop (caught + retried up to
  `AGENT_TASK_MAX_ATTEMPTS`, then `failed`).
- **Same governance**: any tool a background agent invokes still flows through
  the `AgentToolRuntime` — identical allow-list / RBAC / approval / audit. The
  task layer schedules *when* work runs, never widens *what* an agent may do.
- **Integrated like the idle sweeper**: started in the app lifespan via
  `start_background_jobs(background_agents_enabled=…)`, its own poll loop,
  cancelled cleanly on shutdown.
- **Pure, testable core**: `run_once` is driven directly in tests (no sleeping);
  `test_agent_task_runner.py` covers enqueue/idempotency, success, unknown type,
  retry-then-fail, and the concurrency bound.

### Durability note

The in-memory store fits a single app instance (dev + current deploy). For
multi-instance deployments, add a DB-backed `AgentTaskStore` with row-level
claim locking (`SELECT … FOR UPDATE SKIP LOCKED`) — the protocol is already the
seam for it.

## 3. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `FEATURE_AGENT_WRITE_ACTIONS` | `false` | Build/expose write tools (execution still human-approved). |
| `FEATURE_BACKGROUND_AGENTS` | `false` | Start the background task runner. |
| `AGENT_BACKGROUND_CONCURRENCY` | `2` | Max background tasks in flight. |
| `AGENT_BACKGROUND_POLL_SECONDS` | `60` | Runner poll interval. |
| `AGENT_TASK_MAX_ATTEMPTS` | `3` | Retry budget per task. |

## 4. Evaluation & gates

- **Action-safety eval:** `tests/data/action_safety_eval.yaml` +
  `test_action_safety_eval.py` — every write tool is `write` + `human`-gated;
  0 executions without approval; executes after approval; approval doesn't
  bypass RBAC; write tools absent when the build flag is off.
- **Runner:** `test_agent_task_runner.py` (see above).
- **Rollback:** both flags are independently revertible with no schema change;
  turning them off removes write tools and stops the runner.

## 5. Reversibility / blast-radius notes (per write tool)

| Tool | Reversible? | Blast radius | Notes |
|---|---|---|---|
| `entra_unlock_account` | Yes (re-lock) | Single account | Idempotent; safe to retry. |
| `reset_mfa` | Partially (user re-enrols) | Single account | User must re-register MFA afterward. |
| `servicenow_create_incident` | Yes (cancel/close) | One incident record | Idempotent via key; avoids duplicate tickets. |

Auto-execution (`approval=auto_allowlisted`) for any tool requires explicit
security + IT-operations sign-off and a documented blast-radius limit; none are
auto-allowlisted today.

## 6. Versioning

`MCP_PROFILE_VERSION` covers the server scope (ceilings now `WRITE`);
`REGISTRY_VERSION` is `1.2.0`. Audit records `args_hash` + `result_hash` for
every tool call, including approved write executions.
