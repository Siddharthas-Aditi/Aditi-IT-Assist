# MCP Integrations (Phase 7)

> How Aditi Assist agents reach **external IT systems** — Microsoft Graph
> (Entra / Intune / Exchange) and ServiceNow — by acting as an **MCP client**.
> External tools are surfaced into the same governed
> [`AgentToolRuntime`](./agent-tooling.md) as local tools, so they get identical
> allow-list, RBAC, approval, audit, and bounded-loop guarantees.
>
> Status: **landed behind `FEATURE_MCP_TOOLS` (default off), per-server.** All
> Phase-7 tools are **read-only** diagnostics. Writes are Phase 8.

See also: [`agent-tooling.md`](./agent-tooling.md),
[`../../plans/agentic-ops-platform-evolution.md`](../../plans/agentic-ops-platform-evolution.md) (Phase 7).

## 1. Direction: consume, not expose

Phase 7 implements the **consume** direction only: Assist's agents *call* external
MCP servers to diagnose against live systems. Exposing Assist's own capabilities
as an MCP server is explicitly deferred (see the evolution plan §8).

```
specialist agent ── AgentToolRuntime ── McpBackedTool ── McpSession ──▶ MCP server ──▶ Graph / ServiceNow
   (LLM loop)         (one enforcement point)        (protocol)         (allow-listed)
```

## 2. Module map

| Module | Responsibility |
|---|---|
| `app/services/agents/mcp/profiles.py` | `McpServerProfile` registry (`MCP_PROFILE_VERSION`): which servers exist, transport, trust tier, per-server tool allow-list, side-effect ceiling, auth secret *ref*. |
| `app/services/agents/mcp/session.py` | `McpSession` protocol + lazy `SdkMcpSession` adapter (official `mcp` SDK) + `default_session_provider`. The tool layer depends on the protocol, not the SDK. |
| `app/services/agents/mcp/tools.py` | Typed args/result models + `McpBackedTool` + `build_mcp_tools()` (enablement gating, allow-list + ceiling checks). |

## 3. Servers (Phase 7)

| `server_id` | System | Transport | Trust | Tools |
|---|---|---|---|---|
| `msgraph` | Microsoft Graph (Entra / Intune / Exchange) | streamable-http | OFFICIAL | `entra_account_status`, `intune_device_compliance`, `mailbox_quota_status` |
| `servicenow` | ServiceNow ITSM | streamable-http | VENDOR | `servicenow_incident_lookup` |

## 4. Governance properties

- **Allow-list, not auto-discovery.** A server may advertise many tools; only
  names in the profile's `allowed_tools` become callable. An upstream server
  adding a tool can never silently widen agent capability. `build_mcp_tools`
  also rejects (at build time) any binding whose declared side effect exceeds
  the server's `side_effect_ceiling`.
- **Per-server enablement.** A tool is live only when `FEATURE_MCP_TOOLS` is on
  **and** the `server_id` is in `MCP_ENABLED_SERVERS`.
- **Typed end-to-end.** Each MCP tool has a Pydantic args model (validated by
  the runtime before the call) and a Pydantic result model. Server responses are
  mapped into the typed result; unknown fields are preserved under `raw`,
  identifier fields the server omits are backfilled from the request, and an
  unmappable shape still yields a valid (mostly-empty) result rather than raising.
- **RBAC.** Tools require typed permissions: `integration:directory_read`
  (Entra/Intune/Exchange) and `integration:ticketing_read` (ServiceNow), granted
  to `it_agent` and above. Enforced by the runtime, audited on every path.
- **Time-bounded + fail-safe.** Every call is wrapped in
  `MCP_TOOL_TIMEOUT_SECONDS`; a timeout or server error becomes a typed runtime
  `ERROR` outcome (never a crash), so the agent **degrades to KB-only** guidance.
- **Audit with hashes.** The runtime records `args_hash` and `result_hash`
  (SHA-256, truncated) for every call — a complete, tamper-evident trail without
  persisting potentially sensitive payloads.
- **No secrets in profiles.** A profile carries an `auth_secret_ref` (config /
  secrets-manager key name); the token is resolved at connection time.

## 5. How an agent uses an MCP tool

MCP tools are merged into a specialist's runtime via
`build_default_runtime(include_mcp=True)` and gated by the specialist's
`allowed_tools`. Reference wiring:

| Specialist | MCP tool declared |
|---|---|
| `outlook` | `mailbox_quota_status` (confirm a real full-mailbox before steps) |
| `access_mfa` | `entra_account_status` (sign-in / lock / MFA diagnosis) |
| `device_intune` | `intune_device_compliance` (access-block diagnosis) |

`outlook` runs the tool loop today (Phase 5); `access_mfa` / `device_intune`
declare the capability and will use it once they gain the tool-use loop.

## 6. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `FEATURE_MCP_TOOLS` | `false` | Master switch for MCP-backed tools. |
| `MCP_ENABLED_SERVERS` | `[]` | Per-server allow-list, e.g. `["msgraph","servicenow"]`. |
| `MCP_TOOL_TIMEOUT_SECONDS` | `8.0` | Hard timeout per MCP call. |
| `MCP_MSGRAPH_TOKEN` / `MCP_SERVICENOW_TOKEN` | `""` | Auth material (referenced by profiles; set from the secrets manager). |

Enabling, end to end: install the `mcp` SDK, stand up / point at the MCP servers,
populate the auth tokens, set `MCP_ENABLED_SERVERS`, re-run `seed_enterprise`
(to seed the new `integration:*` permissions), then set `FEATURE_MCP_TOOLS=true`.

## 7. Evaluation & tests

- **Contract eval:** `tests/data/mcp_contract_eval.yaml` +
  `test_mcp_contract_eval.py` — every MCP tool maps to a typed spec with
  `mcp_server` set, sits within its server's allow-list and side-effect ceiling,
  declares the right permission, and is rejected without it (0-unauthorized gate).
- **Unit:** `test_mcp_tools.py` — profile registry, enablement gating,
  `McpBackedTool` success / timeout / server-error → graceful ERROR, RBAC and
  allow-list rejection, and audit hashes. Driven by a fake `McpSession` (no SDK,
  no network).
- The live SDK path (`SdkMcpSession`) is covered by integration tests where an
  MCP server is reachable; it is intentionally not in the unit suite.

## 8. Versioning

`MCP_PROFILE_VERSION` bumps on any change to the server set or their declared
scope; `REGISTRY_VERSION` is `1.2.0` (specialists may declare MCP tools). Audit
and analytics join on these.
