# ADR: Autonomous Device Execution — catalog-bound Intune actions (Phase 9)

- **Status**: Accepted (2026-07-03)
- **Deciders**: Platform engineering
- **Supersedes (in part)**: the MCP-boundary rule in
  `docs/architecture/remote-support-decision.md` §"MCP boundary" — that ADR
  stated *"an AI agent must never be able to initiate desktop control."* This
  ADR narrows and replaces that absolute for a **bounded, catalog-limited**
  execution surface. Interactive screen control (Remote Help) remains
  human-only and unchanged.
- **Related**: `docs/architecture/mcp-integrations.md`,
  `docs/architecture/agent-write-actions-and-tasks.md`,
  `docs/architecture/agent-tooling.md`, `docs/security/consent-and-audit.md`

## Context

The business need: let the AI agent **resolve endpoint issues that require
acting on the device** — install a needed tool (Python, Docker Desktop, …), run
a remediation, or take a benign device action — the way an IT specialist would,
grounded in KB/vetted knowledge, with everything audited. The requester chose
**autonomous execution over Intune**, for an org-internal, SSO-authenticated
(Entra) user base.

The unbounded version of that request — "let the agent install *any* software or
run *anything* the internet suggests" — is an LLM-driven remote-code-execution
system on managed endpoints. One poisoned retrieval or prompt injection would be
malware deployed with a valid audit trail. That is rejected.

## Decision

Ship **autonomous execution over a versioned allow-list of pre-published,
risk-tiered actions**. The agent chooses *which* approved action to run and
*whether* to run it; it can never author the payload. Three independent layers,
each a pure/testable module, sit under the existing `AgentToolRuntime`:

1. **Action catalog** (`app/services/agents/device_actions/catalog.py`,
   `CATALOG_VERSION`). Enumerated `APP_CATALOG` / `REMEDIATION_CATALOG` /
   `DEVICE_ACTION_CATALOG`. Each entry maps a stable id → a **pre-published
   Intune object** (Win32 app id / remediation-script id / built-in device
   action) and a `RiskTier`. The agent's only lever is a catalog id — there is
   **no free-form execution surface** for injection to land on.
2. **Autonomy policy** (`policy.py`, `AUTONOMY_POLICY_VERSION`). One pure
   function `evaluate_device_action` → `autonomous | human_approval | deny` from:
   off-catalog ⇒ deny; missing device / failed eligibility / no consent ⇒ deny;
   global kill-switch or injection-scan hit ⇒ human_approval; `HIGH` risk ⇒ never
   autonomous; `MEDIUM` ⇒ autonomous only if explicitly opted in; `LOW` ⇒
   autonomous.
3. **Execution tools** (`tools.py`). Typed `WRITE` `ToolSpec`s
   (`install_win32_app`, `run_remediation_script`, `device_action`) requiring
   `integration:device_execute`. Each tool resolves the catalog entry, runs the
   policy, and only then calls the Intune exec MCP server — using the *catalog's*
   published Intune id as the payload. Off-catalog / high-risk / suspicious ⇒
   typed non-executing result (`denied` / `needs_approval`), no server call.

**MCP surface.** A dedicated server profile `msgraph_intune_exec`
(`MCP_SERVER_REGISTRY`, `MCP_PROFILE_VERSION` → 1.1.0), separate from the
read-only `msgraph` profile so the high-blast-radius surface has its own
enablement, allow-list, and audit boundary. Reachable only when
`FEATURE_DEVICE_EXECUTION` is on **and** the server is in `MCP_ENABLED_SERVERS`.
Dev/staging use `MCP_USE_MOCK` for a fully exercisable mock — same governance,
no real Graph.

**Two independent gates**, mirroring Phase 8: a **build gate**
(`FEATURE_DEVICE_EXECUTION` — tools aren't even constructed otherwise) and an
**autonomy gate** (`DEVICE_EXECUTION_AUTONOMOUS` — when off, *every* action
routes to human approval even with the feature on). `DEVICE_EXECUTION_AUTONOMOUS_MEDIUM`
opts medium-risk into autonomy; high-risk is never autonomous under any config.

## Prompt-injection posture

- **Structural, not vibes.** The primary defense is that the tool args carry no
  runnable content — only a catalog id, device id, idempotency key, and a
  justification string that is *scanned but never executed*. An injected
  instruction has nowhere to run.
- **Scanner as a tripwire.** `scan_for_injection` downgrades a suspicious request
  to human approval; it never *expands* capability.
- **RBAC + SSO.** `integration:device_execute` is granted to it_lead+ (higher bar
  than Phase-7 reads). The autonomous agent runs under a service principal that
  holds it; combined with Entra SSO, only Aditi identities are in play.
- **Consent + eligibility.** Execution requires a live consent record for the
  target employee and a passed Intune eligibility/compliance precheck (the
  `GuardrailProvider` seam), reusing the remote-support consent model.

## Safety rules encoded (eval-asserted)

`backend/tests/data/device_execution_safety_eval.yaml` +
`tests/unit/test_device_execution_safety_eval.py` pin two hard gates:

- **0 autonomous executions above the risk threshold** (HIGH never autonomous;
  MEDIUM only when opted in);
- **0 executions of anything off-catalog**.

Plus contract pins (typed WRITE spec, `integration:device_execute`, exec-server
allow-list) and full dispatch tests (unauthorized rejected; low-risk executes;
high-risk / off-catalog / injection held or denied with no server call).

## Consequences

- Real autonomous remediation for the common, low-risk cases (install a vetted
  dev tool, flush DNS, sync a device) with no human in the loop — while the
  dangerous long tail is structurally impossible or human-gated.
- Adding a runnable action is a reviewed, versioned change: one catalog entry +
  a published Intune object. Reviewers see exactly what capability changed via
  the bumped `CATALOG_VERSION`.
- Every call is audited by the runtime with arg/result hashes; the typed result
  records the decision, risk tier, and policy signals.
- **Not built:** free-form scripts, arbitrary installers, destructive actions,
  unattended access without consent. Those remain out of scope and would require
  a superseding ADR.

## Follow-ups

Done (iterations 2–3):
- `DeviceExecutionService` + `/device-execution` API (catalog, request, approve, reject).
- Human-approval decisions parked in the shared approval queue (`/agent-ops/approvals`);
  approve re-checks consent + re-dispatches via `execute_approved`.
- Real guardrails: Intune-compliance eligibility + `RemoteSupportConsent` lookup,
  enforced in the **tool layer** (device-owner resolution) so consent is re-checked on
  every path; permissive only under `MCP_USE_MOCK`.
- Frontend **Device Actions** page (`/operations/device-actions`) + feature module.

Still open:
- Employee-facing "a fix was applied to your device" notice.
- `scripts/validate_device_catalog.py` to assert every catalog Intune id exists in
  the tenant at boot (prod).
- Real `msgraph_intune_exec` MCP server behind `MCP_USE_MOCK=false`.

Sources: [Intune Win32 app management](https://learn.microsoft.com/en-us/intune/intune-service/apps/apps-win32-app-management),
[Intune remediations](https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/remediations),
[managedDevice actions (Graph)](https://learn.microsoft.com/en-us/graph/api/resources/intune-devices-manageddevice?view=graph-rest-1.0)
