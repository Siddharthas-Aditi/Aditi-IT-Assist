# Plan: Autonomous Device Execution (Phase 9)

Goal: let the agent resolve endpoint issues by acting on Intune-managed devices
(install approved apps, run approved remediations, benign device actions),
grounded in KB, autonomous for low-risk, human-approved above threshold, fully
audited. ADR: `docs/architecture/device-execution-decision.md`.

## Delivered in this iteration

- [x] **Action catalog** — `device_actions/catalog.py`, versioned, risk-tiered;
      Python + Docker Desktop + VS Code + Node apps, LOW/MED/HIGH remediations,
      sync/restart device actions. Agent selects ids only; no payload authoring.
- [x] **Autonomy policy** — `device_actions/policy.py`, pure
      `evaluate_device_action` (autonomous/human_approval/deny) + `scan_for_injection`.
- [x] **Execution tools** — `device_actions/tools.py`: `install_win32_app`,
      `run_remediation_script`, `device_action` (typed WRITE, catalog+policy gated).
- [x] **Exec MCP server** — `msgraph_intune_exec` profile (own enablement/allow-list);
      mock responses; `MCP_PROFILE_VERSION` → 1.1.0.
- [x] **RBAC** — `integration:device_execute` (it_lead+, high-risk, consent-required, audited).
- [x] **Config** — `FEATURE_DEVICE_EXECUTION`, `DEVICE_EXECUTION_AUTONOMOUS`,
      `DEVICE_EXECUTION_AUTONOMOUS_MEDIUM`; prod fail-fast validations.
- [x] **Wiring** — `build_default_runtime(include_device_execution=True)`;
      `device_intune` specialist allow-list; `TOOL_REGISTRY_VERSION`/`REGISTRY_VERSION` bumps.
- [x] **Evals + unit tests** — safety eval (0-autonomous-above-threshold,
      0-off-catalog) + catalog/policy/tool tests.
- [x] **Docs** — ADR, mechanics doc, this plan, CLAUDE.md section.

## Delivered in iteration 2

- [x] **DeviceExecutionService** — end-to-end router: request → guardrails →
      policy → (autonomous execute | queue for approval | deny), plus an
      `approve` path that re-checks consent/eligibility before executing.
- [x] **Approval-queue integration** — device tools are now `approval=human` and
      dispatchable from the shared queue; `human_approval` decisions are parked via
      `ApprovalQueue.propose` and appear in `GET /agent-ops/approvals`. Approve
      re-dispatches through `execute_approved` with the scoped token.
- [x] **Real GuardrailProvider** — `guardrails.py`: eligibility via the Intune
      compliance MCP read; consent via a `RemoteSupportConsent` lookup (permissive
      only under `MCP_USE_MOCK`).
- [x] **API + schemas** — `/device-execution` router (catalog, actions, approve,
      reject); `schemas/device_execution.py`.
- [x] **Kill-switch honoured in routing** — `DEVICE_EXECUTION_AUTONOMOUS` threaded
      into the service's policy inputs (was defaulted-on before).
- [x] **Tests** — `test_device_execution_service.py` (full routing + approve path);
      updated `test_device_execution_safety_eval.py` for the human-gated contract.

## Delivered in iteration 3

- [x] **Consent enforced in the tool layer** — `DeviceGuardrails` resolves the
      device owner server-side (Intune primary user) and checks consent there, so
      consent is re-verified on **every** path (autonomous, device-endpoint approve,
      and the generic `/agent-ops` approval queue). Closes the earlier gap.
- [x] **Frontend** — `features/device-execution/` (typed API + hooks) + the
      **Device Actions** page (`/operations/device-actions`) with catalog picker,
      request form, and typed outcome; nav entry added. `tsc` + `eslint` clean.

## Follow-ups (next iterations)

- [ ] **Catalog validator** — `scripts/validate_device_catalog.py` asserting each
      Intune id exists in the tenant at boot (prod).
- [ ] **Real exec MCP server** — implement the `msgraph_intune_exec` server against
      Graph (Win32 app assignment, remediation on-demand, `managedDevice` actions).
- [ ] **Per-device idempotency store** — dedupe on `idempotency_key` server-side.
- [ ] **Employee-facing notice** — "an approved fix was applied to your device"
      surfaced in the employee chat/notifications (device request/approve UI is done).
- [x] **Consent on the generic approvals path** — closed: consent is now enforced in
      the tool layer (device-owner resolution), so approving via either
      `/agent-ops/approvals` or `/device-execution/approvals` re-checks consent.
- [ ] **Background remediation agent** — optional Phase-8 background task that runs
      low-risk catalog remediations proactively (behind `FEATURE_BACKGROUND_AGENTS`).

## Out of scope (would need a superseding ADR)

- Free-form scripts / arbitrary installers / commands authored by the LLM.
- Destructive actions (wipe, disable security controls).
- Unattended execution without a consent record.
