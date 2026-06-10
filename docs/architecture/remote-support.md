# Remote Support Architecture

> **Aditi IT Assist** — remote assistance orchestration layer.
> Last updated: June 2026

---

## Overview

The remote support system enables IT agents to view or control employee screens
through a **provider abstraction layer** that decouples the application from any
specific remote-desktop tool. Microsoft Remote Help (via Microsoft Intune) is the
default provider; the abstraction supports plug-in of additional providers without
changing business logic.

All sessions require **explicit employee consent** before any connection is
permitted. Consent is immutable once recorded. Employees may revoke at any time
during a session.

---

## Provider Abstraction

```
┌────────────────────────────────────────────────────────────────┐
│                     RemoteSupportService                       │
│  (orchestration, consent, lifecycle, audit)                    │
└────────────────────┬───────────────────────────────────────────┘
                     │ depends on
                     ▼
        ┌────────────────────────┐
        │  RemoteSupportProvider │  ← Abstract Base Class
        │  (base.py)             │
        └────────────┬───────────┘
                     │ implements
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
 MicrosoftRemoteHelp      (future providers)
 Provider                  • AnyDesk
 (stub — Graph API)        • TeamViewer
                           • Zoho Assist
```

### `RemoteSupportProvider` interface

| Method | Required | Description |
|--------|----------|-------------|
| `create_session()` | ✅ | Create a session at the provider; returns join URLs |
| `terminate_session()` | ✅ | Force-close a provider session |
| `get_session_status()` | ✅ | Poll provider for current status |
| `get_session_recording_url()` | ❌ | Optional: recording URL if provider supports it |
| `validate_prerequisites()` | ❌ | Check preconditions before session create |
| `health_check()` | ❌ | Verify provider API connectivity |

### Adding a New Provider

1. Create `backend/app/services/remote_support/providers/<name>.py`
2. Subclass `RemoteSupportProvider` and implement the three required methods
3. Register the instance in `RemoteSupportService._build_providers()`
4. Set `REMOTE_SUPPORT_PROVIDER=<name>` in environment config

---

## Session Lifecycle

```
   [Agent requests session]
            │
            ▼
       ┌─────────┐
       │requested│
       └────┬────┘
            │ send_consent_request()
            ▼
   ┌─────────────────┐         consent window
   │ consent_pending  │──────── expires ──────► expired
   └────────┬────────┘
            │
     ┌──────┴──────┐
     │ employee    │
     │ responds    │
     └──────┬──────┘
            │
     ┌──────▼──────┐        ┌───────────────┐
     │consent_deni │        │consent_granted │
     │   (terminal)│        └───────┬────────┘
     └─────────────┘                │ launch_session()
                                    ▼
                              ┌──────────┐
                              │connecting│
                              └────┬─────┘
                                   │ mark_connected()
                                   ▼
                              ┌────────┐
                              │ active │◄──── paused
                              └────┬───┘         ▲
                                   │             │
                           end / revoke / error
                                   │
                        ┌──────────▼──────────┐
                        │completed / terminated│
                        │     (terminal)       │
                        └─────────────────────┘
```

### Status Definitions

| Status | Description |
|--------|-------------|
| `requested` | Agent has submitted request; not yet sent to employee |
| `consent_pending` | Consent notification delivered to employee |
| `consent_granted` | Employee approved; agent can launch provider session |
| `consent_denied` | Employee denied; terminal state |
| `connecting` | Provider session created; waiting for both parties to join |
| `active` | Both parties connected; session is live |
| `paused` | Session temporarily paused (provider-level) |
| `completed` | Normal end by participant |
| `terminated` | Forced end (revocation, admin, error, timeout) |
| `expired` | Consent window elapsed without employee response |

---

## Session Types & Permissions

| Session Type | Capabilities | Minimum Role | Justification |
|---|---|---|---|
| `screen_view` | View screen, annotate | `it_agent` | Optional |
| `screen_control` | View + keyboard/mouse control | `it_lead` | **Required** |

`screen_control` is a high-risk permission. The backend service enforces:
- Role check on every `request_session()` call
- Justification stored in session record
- Verbatim `SCREEN_CONTROL` consent notice shown to employee

---

## Microsoft Remote Help Integration

File: `backend/app/services/remote_support/providers/microsoft_remote_help.py`

**Current state:** STUB — returns mock data for development. Production integration
requires a Microsoft Intune + Remote Help license and Azure AD app registration.

### Production Implementation Path

```http
# 1. Acquire token
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token

# 2. Create session
POST https://graph.microsoft.com/beta/deviceManagement/remoteAssistanceSessions

# 3. Poll status
GET  https://graph.microsoft.com/beta/deviceManagement/remoteAssistanceSessions/{id}

# 4. Terminate
DELETE https://graph.microsoft.com/beta/deviceManagement/remoteAssistanceSessions/{id}
```

### Capabilities

| Capability | Supported |
|---|---|
| `screen_view` | ✅ |
| `screen_control` | ✅ |
| `chat` | ✅ |
| `annotation` | ✅ |
| `multi_monitor` | ✅ |
| `file_transfer` | ❌ |
| `unattended` | ❌ (roadmap) |

---

## Unattended Access (Roadmap)

Unattended remote access (no employee present) is architecturally modeled but
intentionally **not implemented** in the current version.

Design constraints when implemented:
- Requires separate consent type: `unattended_access`
- Must be pre-authorized by the employee + IT Lead
- Limited to specific device management tasks (patch, inventory)
- Full session recording mandatory
- Automatic expiry after single use
- `RemoteSupportProvider.supports_unattended` defaults to `False`

---

## Data Model

```
RemoteSupportSession           RemoteSupportConsent
───────────────────            ────────────────────
id (PK, UUID)                  id (PK, UUID)
employee_id → users            session_id → sessions
agent_id → users               employee_id → users
ticket_id → tickets (opt)      consent_type (enum)
session_type (enum)            granted (bool)
status (enum)                  consented_at (immutable)
provider (str)                 consent_text_shown (full text)
provider_session_id            ip_address
join_url_agent                 user_agent
join_url_employee              revoked_at (nullable)
join_code                      revocation_reason
requested_at                   denial_reason
consent_sent_at
consent_deadline               RemoteSessionEvent
started_at                     ─────────────────
ended_at                       id (PK, UUID)
max_duration_minutes           session_id → sessions
justification                  event_type (enum)
policy_check_passed            actor_id → users (opt)
termination_reason             occurred_at
resolution_notes               description
actions_taken (JSON array)     metadata (JSONB)
provider_metadata (JSONB)      ip_address
```

### Key Invariants

1. `RemoteSupportConsent.consented_at` — **never updated after insert**
2. `RemoteSessionEvent` rows — **never deleted**
3. Session status only moves forward through `_ALLOWED_TRANSITIONS`
4. `join_url_agent` / `join_url_employee` — **only populated after `launch_session()`**

---

## API Endpoints

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/remote-support/sessions` | it_agent | Request session + send consent |
| `GET` | `/remote-support/sessions` | scoped | List sessions (role-scoped) |
| `GET` | `/remote-support/sessions/{id}` | participant | Full session detail |
| `GET` | `/remote-support/sessions/{id}/status` | participant | Poll provider status |
| `POST` | `/remote-support/sessions/{id}/launch` | it_agent | Launch after consent granted |
| `POST` | `/remote-support/sessions/{id}/connected` | it_agent | Mark as connected |
| `POST` | `/remote-support/sessions/{id}/end` | participant | End session |
| `PUT` | `/remote-support/sessions/{id}/resolution` | it_agent | Update resolution notes |
| `GET` | `/remote-support/sessions/{id}/consent-info` | employee | Consent modal payload |
| `POST` | `/remote-support/sessions/{id}/consent` | employee | Grant or deny consent |
| `POST` | `/remote-support/sessions/{id}/revoke` | employee | Revoke mid-session |
| `GET` | `/remote-support/my-sessions` | employee | Own session history |
| `GET` | `/remote-support/provider/health` | it_agent | Provider health check |

---

## Frontend Components

| Component | Path | Used By |
|---|---|---|
| `RemoteAssistPage` | `pages/operations/RemoteAssistPage.tsx` | IT agent — session management |
| `ConsentModal` | `components/remote-support/ConsentModal.tsx` | Employee — consent flow |
| `ActiveSessionBanner` | `components/remote-support/ActiveSessionBanner.tsx` | Employee — in-session indicator |

### Employee Consent Flow

```
Employee receives notification (push / email)
       │
       ▼
  [ConsentModal opens]
       │ reads full consent notice
       │ (scroll-to-bottom enforced before Grant is enabled)
       │
  ┌────┴────┐
  │Grant    │   POST /consent { granted: true }
  │         │──────────────────────────────────► Agent notified
  │Deny     │   POST /consent { granted: false } → session terminated
  └─────────┘
       │ during active session
       ▼
  [ActiveSessionBanner]
       │ "End Session" clicked
       ▼
  POST /revoke → session terminated immediately
```

---

## Configuration

| Environment Variable | Description | Default |
|---|---|---|
| `REMOTE_SUPPORT_PROVIDER` | Active provider name | `microsoft_remote_help` |
| `AZURE_TENANT_ID` | Azure AD tenant ID | — |
| `AZURE_CLIENT_ID` | App registration client ID | — |
| `AZURE_CLIENT_SECRET` | App registration secret | — |

---

## Observability

| Metric | Description | Alert |
|---|---|---|
| Session consent rate | % of sessions where consent is granted | < 50% sustained |
| Consent window expiry rate | % that expire before employee responds | > 20% |
| Provider error rate | Failures in `create_session` / `terminate_session` | > 5% |
| `screen_control` usage | High-risk session type frequency | > 20% of total |
| Session duration | Average duration by type | > 45 min avg |

All lifecycle transitions are recorded in `RemoteSessionEvent` and queryable
via the audit log viewer.

- Generic provider interface for alternatives

## Session Lifecycle

```
┌──────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────┐     ┌───────────┐
│ Requested │────▶│ Consent Pending│────▶│Consent Granted│───▶│ Active  │───▶│ Completed │
└──────────┘     └───────────────┘     └─────────────┘     └────────┘     └───────────┘
                        │                                         │
                        ▼                                         ▼
                 ┌──────────────┐                          ┌────────────┐
                 │Consent Denied│                          │ Terminated │
                 └──────────────┘                          └────────────┘
```

## Session Types

| Type | Permission Required | Description |
|------|-------------------|-------------|
| `screen_view` | `it_agent` + | View employee's screen (read-only) |
| `screen_control` | `it_lead` + | Take control of employee's screen |
| `full_remote` | `it_admin` only | Full unattended remote (future) |

## Consent Model

All attended remote support REQUIRES explicit employee consent:

1. IT agent initiates request with justification
2. Employee receives consent modal in their UI
3. Employee explicitly approves or denies
4. Consent record created with IP address and timestamp
5. Session cannot start without valid consent
6. Employee can revoke consent at any time (terminates session)

### Consent Record Fields
- `session_id` — linked remote session
- `employee_id` — who granted consent
- `consent_type` — what access was granted
- `granted` — true/false
- `granted_at` — timestamp
- `revoked_at` — if employee later revokes
- `ip_address` — audit trail
- `consent_message` — human-readable description

## Policy Enforcement

```python
def _check_policy(agent, session_type):
    # Screen view: any IT staff
    # Screen control: it_lead or above
    # Full remote: it_admin only (future, with stronger approval)
```

## Provider Interface

```python
class RemoteSupportProvider(ABC):
    provider_name: str
    create_session(agent_id, employee_id, session_type) -> RemoteSessionInfo
    terminate_session(provider_session_id) -> bool
    get_session_status(provider_session_id) -> str
```

## Microsoft Remote Help Integration (Planned)

### Prerequisites
1. Azure AD App Registration with Remote Help permissions
2. Microsoft Intune license (E3/E5 or Intune standalone)
3. Remote Help app on managed devices
4. Conditional Access policies configured

### Integration Points
- Microsoft Graph API: `/deviceManagement/remoteAssistancePartners`
- Session initiation via Graph API
- Real-time status via webhooks/polling
- Session recording metadata (if configured)

## Audit Trail

Every remote support action is logged:
- Session requested (who, why, what type)
- Consent granted/denied
- Session started
- Session ended
- Actions taken during session (metadata)
- Resolution notes post-session
