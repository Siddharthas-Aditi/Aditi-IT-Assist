# ADR: Remote Support Provider — Microsoft Remote Help (Intune-native)

- **Status**: Accepted (2026-07-02)
- **Deciders**: Platform engineering
- **Related**: `docs/architecture/remote-support.md` (mechanics),
  `docs/security/consent-and-audit.md`, `docs/architecture/mcp-integrations.md`

## Context

Aditi IT Assist needs production-grade remote assistance for issues that AI
chat and KB-guided troubleshooting can't resolve. The orchestration layer
(session lifecycle, consent, RBAC, audit — `app/services/remote_support/`)
already exists and is tested; the provider adapter was a mock. We evaluated:

1. **Microsoft Remote Help** (Intune-native remote assistance)
2. **Intune + TeamViewer connector**
3. Other enterprise tools (BeyondTrust, ScreenConnect) / custom WebRTC

## Environment facts (verified 2026-07-02)

- The **legacy Intune TeamViewer connector is deprecated** and retires April
  2027. The replacement connector (April 2026) requires **TeamViewer Tensor**
  licensing and devices **actively managed by TeamViewer** — an entire second
  device-management plane plus a per-seat license we don't own.
- **There is no public Microsoft Graph API that programmatically creates an
  attended Remote Help session.** Sessions are launched from the Intune admin
  center (device ▸ *New remote assistance session*) or the Remote Help app
  with a session-code exchange. Graph does expose:
  - `deviceManagement/remoteAssistanceSettings` (beta) — tenant Remote Help
    configuration (used for provider health/prereq checks),
  - `deviceManagement/managedDevices` — enrollment/compliance lookups (used
    for device eligibility pre-checks; same Graph app registration as our
    Phase-7 MCP tools).
- Aditi's estate is Microsoft-centric: Entra ID, Intune-managed endpoints,
  Exchange Online, Azure OpenAI. Our MCP layer already talks to Graph.

## Decision

**Microsoft Remote Help is the primary provider.** The adapter is an *honest
orchestrator*, not a fake session API:

- **Platform owns**: session records, consent (immutable, time-boxed),
  RBAC (`remote:*` permissions; screen-control requires it_lead+ and
  justification), audit events, ticket + live-chat linkage, expiry/duration
  timers, status visibility.
- **Remote Help owns**: the pixel transport — Entra-authenticated helper and
  sharer, Intune conditional-access and RBAC enforcement, attended consent in
  the Remote Help client itself (defense in depth with our consent gate).
- **Launch model**: on `launch`, the adapter (a) validates prerequisites via
  Graph (tenant Remote Help enabled, device enrolled/compliant), (b) returns
  the helper a deterministic **Intune admin-center device launch URL** and the
  employee clear join instructions for the Remote Help app, (c) records
  everything. Status transitions (`connected`, `ended`) are driven by our
  endpoints, as today; if Microsoft ships a session API, the adapter absorbs
  it without touching the service layer.
- **Dev/staging**: `REMOTE_SUPPORT_USE_MOCK=true` (default) keeps the fully
  functional mock adapter, mirroring the `MCP_USE_MOCK` pattern, so the whole
  workflow is exercisable locally with zero Azure dependencies.

**TeamViewer (new Tensor connector)** remains a documented alternative behind
the same `RemoteSupportProvider` ABC for a future where non-Intune devices
need coverage. Not implemented now: extra license + management plane, and the
legacy connector is on a deprecation path.

**Custom WebRTC screen sharing is rejected** outright: building consent-safe,
audited, enterprise-compliant remote control in-house is a security liability
and duplicates a tool the org already licenses.

## MCP boundary (why the provider is NOT an MCP tool)

MCP tools are for **agent tool-calling** — bounded, typed calls an LLM may
select inside `AgentToolRuntime`. A remote-control session is a long-lived,
human-owned, consent-gated domain object with DB state; an AI agent must never
be able to initiate desktop control. Therefore:

- The provider integrates via the existing `RemoteSupportProvider` ABC inside
  the service layer, with human-only API endpoints (RBAC-guarded).
- The AI chat path may **suggest** remote assistance in an escalation offer,
  but session creation always happens through the specialist's authenticated
  action — same discipline as ticket persistence (offer → explicit action).
- Graph *read* lookups used for eligibility (device enrollment/compliance)
  reuse the MCP-governed msgraph tooling pattern and credentials, keeping one
  audited Graph integration surface.

## Safety rules encoded

- Attended-only. `supports_unattended` is False; unattended access is out of
  scope until a written policy exists (this ADR must be superseded first).
- Consent is required, immutable, time-boxed (10-min window), revocable
  mid-session; revocation terminates the session immediately.
- Screen control requires elevated role + justification; view-only is default.
- Every transition is an append-only `RemoteSessionEvent`; sessions link to
  ticket and live-chat session for a complete audit chain.
- Sessions auto-expire: consent deadline passes ⇒ `expired`; max duration
  exceeded ⇒ terminated by sweeper (`ended_by_timeout` analog).

## Consequences

- Zero new licenses; leverages existing Intune + Entra investment.
- No fabricated Graph calls — the integration only claims what the API
  actually supports, so staging validation is truthful.
- Helper launch is one click to the right Intune blade rather than a fully
  headless handoff; acceptable for specialist workflows, and the seam is in
  the adapter if Microsoft ships session-creation APIs.

Sources: [Remotely administer devices in Microsoft Intune](https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/teamviewer-support),
[TeamViewer legacy connector](https://learn.microsoft.com/en-us/intune/device-management/tools/teamviewer-legacy),
[remoteAssistanceSettings (Graph beta)](https://learn.microsoft.com/en-us/graph/api/resources/intune-remoteassistance-remoteassistancesettings?view=graph-rest-beta)
