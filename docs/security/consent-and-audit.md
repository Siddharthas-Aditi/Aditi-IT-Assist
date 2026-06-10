# Consent & Audit — Remote Support Security Model

> **Aditi IT Assist** security reference for remote support sessions.
> Last updated: June 2026

---

## Purpose

This document defines the consent model, audit event schema, data retention
policy, and compliance considerations for the remote support subsystem. It is
the reference for security reviews, privacy impact assessments, and regulatory
audits.

---

## Consent Model

### Principles

1. **Voluntariness** — Consent is always optional. Employees cannot be penalised
   for refusing.
2. **Informed consent** — The verbatim consent notice is stored alongside the
   consent decision so auditors can verify exactly what text the employee saw.
3. **Specificity** — Each consent is tied to a single session and a specific
   session type (`screen_view` or `screen_control`). A consent for one session
   cannot be reused.
4. **Revocability** — Employees may revoke at any time. Revocation terminates
   the session immediately at the provider level.
5. **Immutability** — The original `consented_at` timestamp is never modified.
   Revocation adds `revoked_at` to the same row but does not delete or overwrite
   the original grant.

### Consent Window

Employees have **10 minutes** (`CONSENT_WINDOW_MINUTES`) to respond to a consent
request. If the window lapses without a response:
- Session transitions to `expired`
- No provider session is ever created
- Agent must make a new request

The countdown is shown live in the `ConsentModal` UI component.

### What Is Stored in `RemoteSupportConsent`

| Field | Content | Mutability |
|-------|---------|------------|
| `id` | UUID primary key | Immutable |
| `session_id` | FK to session | Immutable |
| `employee_id` | FK to user | Immutable |
| `consent_type` | `screen_view` \| `screen_control` | Immutable |
| `granted` | `true` or `false` | Immutable |
| `consented_at` | UTC timestamp of decision | **Immutable** |
| `consent_text_shown` | Verbatim notice text at time of decision | Immutable |
| `ip_address` | Employee's IP address | Immutable |
| `user_agent` | Browser user-agent string | Immutable |
| `revoked_at` | UTC timestamp of revocation (if any) | Set once on revoke |
| `revocation_reason` | Employee's stated reason (optional) | Set once on revoke |
| `denial_reason` | Employee's reason for denying (if denied) | Immutable |

### Consent Notice Text (verbatim, as shown to employees)

**Screen View:**
```
An IT support agent has requested to view your screen to assist with your
support request. During this session, the agent will be able to see everything
on your screen. You can end the session at any time by clicking the
"End Session" button. Your consent is voluntary.
```

**Screen Control:**
```
An IT support agent has requested to take control of your screen and keyboard
to assist with your support request. During this session, the agent will be able
to see and interact with your screen. You can end the session at any time by
clicking the "End Session" button. Your consent is voluntary.
```

These strings are defined as constants in
`backend/app/services/remote_support/service.py` (`CONSENT_NOTICES` dict).
Any change to the notice text must be reviewed by Legal.

### UI Consent Safeguards

The `ConsentModal` React component enforces:
- Employee must **scroll to the bottom** of the consent notice before the
  **Grant Access** button becomes active
- **Countdown timer** is always visible
- High-risk sessions (`screen_control`) display an amber warning banner
- Deny requires a two-step confirmation with optional reason

---

## Audit Event Schema

Every lifecycle transition and policy decision is recorded in
`RemoteSessionEvent`. These rows are **append-only** and are never deleted.

### Event Types

| `event_type` | Trigger | Actor |
|---|---|---|
| `requested` | Agent calls `request_session()` | Agent |
| `consent_sent` | `send_consent_request()` called | Agent |
| `consent_granted` | Employee grants consent | Employee |
| `consent_denied` | Employee denies consent | Employee |
| `consent_revoked` | Employee revokes mid-session | Employee |
| `session_launched` | `launch_session()` succeeds | Agent |
| `session_connected` | `mark_connected()` called | Agent |
| `session_paused` | Session paused at provider | Provider/Agent |
| `session_ended` | Normal end by any participant | Participant |
| `status_updated` | Provider status poll found a change | System |
| `resolution_added` | Agent updates resolution notes | Agent |

### Event Schema

```python
RemoteSessionEvent:
  id            UUID          # unique event id
  session_id    UUID          # FK to session
  event_type    str           # one of the types above
  actor_id      UUID | None   # who triggered the event (NULL = system)
  occurred_at   datetime      # UTC
  description   str | None    # human-readable summary
  metadata      JSONB | None  # structured context (steps, provider_session_id, etc.)
  ip_address    str | None    # network address of the actor
```

### Immutability Enforcement

- **No `UPDATE` statements** are ever issued against `remote_session_events`
- **No `DELETE` statements** are ever issued against `remote_session_events`
- Database-level `CHECK` constraints and row-level security should be added
  in production to enforce this at the storage layer

---

## Termination Reasons

When a session ends abnormally, `RemoteSupportSession.termination_reason`
records why. These values are also logged in the final `session_ended` event.

| Reason | Description |
|--------|-------------|
| `completed` | Normal end, issue resolved |
| `employee_revoked` | Employee revoked consent mid-session |
| `agent_ended` | Agent ended the session |
| `admin_terminated` | IT Lead or Admin force-closed the session |
| `consent_expired` | Consent window elapsed before employee responded |
| `consent_denied` | Employee denied the initial consent request |
| `provider_error` | External provider reported an error |
| `max_duration_exceeded` | Session ran past `max_duration_minutes` |

---

## High-Risk Permission Flags

`screen_control` sessions are subject to additional controls:

| Control | Description |
|---------|-------------|
| Role enforcement | Only `it_lead` / `it_admin` may request |
| Mandatory justification | Free-text justification stored in session record |
| Elevated consent notice | Amber warning in consent modal; explicit "Full Control" label |
| Audit event tagging | All events tagged with `session_type: screen_control` |
| Review queue (roadmap) | Auto-flag for IT Lead review in sessions > 30 min |

---

## Data Retention Policy

| Data | Retention | Reason |
|------|-----------|--------|
| `RemoteSupportSession` | 2 years | Support case reference |
| `RemoteSupportConsent` | 7 years | Legal compliance / labour law |
| `RemoteSessionEvent` | 7 years | Regulatory audit trail |
| Join URLs / codes | Cleared on session end | PII minimisation |
| `provider_metadata` (JSONB) | 2 years | Provider-specific debug data |
| Agent / employee names in events | 7 years (via FK) | Audit linkage |

**After the retention period:**
- Session and event rows should be anonymised (replace `employee_id` / `agent_id`
  with a hashed identifier), not deleted, to preserve aggregate statistics.
- Provider session IDs and join codes should be nulled.

---

## GDPR / Privacy Considerations

| Item | Treatment |
|------|-----------|
| Consent record | Lawful basis = explicit consent (Art. 6(1)(a)) |
| `consent_text_shown` | Required to demonstrate informed consent |
| IP address in events | Legitimate interest for security; retained 7 years |
| Screen content | Never stored by Aditi — processed only by provider |
| Right to erasure | Consent rows are anonymised, not erased (audit integrity) |
| Data subject access | Employees can request their session history via `/my-sessions` |
| Cross-border transfer | Verify provider (MS Remote Help) SCCs or adequacy decision |

---

## Access Control Matrix

| Role | Can Request | Can View Own Sessions | Can View All Sessions | Can Terminate Any |
|------|-------------|----------------------|----------------------|-------------------|
| `employee` | ❌ | ✅ | ❌ | Only own |
| `it_agent` | ✅ (view only) | ✅ | Own assigned | ✅ own |
| `it_lead` | ✅ (view + control) | ✅ | ✅ | ✅ |
| `it_admin` | ✅ | ✅ | ✅ | ✅ |
| `security_auditor` | ❌ | ✅ | ✅ (read-only) | ❌ |

`security_auditor` has read access to the full audit trail but cannot initiate
or modify sessions.

---

## Platform Audit Log (General)

The general `AuditEvent` model (separate from `RemoteSessionEvent`) covers all
platform actions:

```python
AuditEvent:
  actor_id       — Who performed the action
  actor_email    — Denormalized for search
  actor_role     — Role at time of action
  action         — What was done (verb)
  resource_type  — What type of thing was affected
  resource_id    — Specific resource identifier
  description    — Human-readable description
  old_value      — Previous state (sanitized)
  new_value      — New state (sanitized)
  ip_address     — Client IP
  user_agent     — Client user agent
  severity       — info | warning | critical
  created_at     — Immutable timestamp
```

Remote support events are recorded in *both* `RemoteSessionEvent` (per-session
detail) and the platform `AuditEvent` log (cross-resource audit trail).

---

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Agent accesses employee screen without consent | Consent enforced in `launch_session()` — `ConsentRequired` exception if no valid consent |
| Agent forges consent | Consent created only by employee-authenticated endpoint; FK to `employee_id` |
| Replay attack on consent | Consent is single-use; revocation sets `revoked_at` |
| Agent exceeds session scope (screen_control without role) | `_enforce_request_policy()` checks roles on every request |
| Session left open after issue resolved | `max_duration_minutes` hard cap; agent end-of-session flow required |
| Employee unaware session is active | `ActiveSessionBanner` shown throughout session; consent deadline countdown |
| Audit log tampering | Append-only model; no update/delete paths in service layer |
| Provider credential leak | Secrets stored in environment variables, never in code or DB |

---

## Security Review Checklist

Before deploying remote support to production:

- [ ] `AZURE_CLIENT_SECRET` rotated from dev stub value
- [ ] Production provider endpoints tested with real Graph API calls
- [ ] Consent notice text reviewed and approved by Legal
- [ ] DB-level `ROW SECURITY` or `CHECK` added to `remote_session_events`
- [ ] `max_duration_minutes` ceiling confirmed with IT policy team
- [ ] Employee notification mechanism (WebSocket / push) implemented
- [ ] Session recording (if enabled in MS Remote Help) reviewed for storage compliance
- [ ] Penetration test covers consent bypass and session hijack scenarios
- [ ] Retention / anonymisation job scheduled
- [ ] `security_auditor` role can query event log in Audit Log Viewer UI

Every security-relevant action is logged immutably:

```python
AuditEvent:
  actor_id       — Who performed the action
  actor_email    — Denormalized for search
  actor_role     — Role at time of action
  action         — What was done (verb)
  resource_type  — What type of thing was affected
  resource_id    — Specific resource identifier
  description    — Human-readable description
  old_value      — Previous state (sanitized)
  new_value      — New state (sanitized)
  ip_address     — Client IP
  user_agent     — Client user agent
  severity       — info | warning | critical
  created_at     — Immutable timestamp
```

## Audited Actions

| Action | Resource | Severity | Trigger |
|--------|----------|----------|---------|
| `user.login` | user | info | Successful login |
| `user.login_failed` | user | warning | Failed login attempt |
| `user.logout` | user | info | User logout |
| `user.role_changed` | user | warning | Role assignment modified |
| `user.created` | user | info | New user registered |
| `user.deactivated` | user | warning | User account disabled |
| `ticket.created` | ticket | info | New ticket created |
| `ticket.status_changed` | ticket | info | Status transition |
| `ticket.assigned` | ticket | info | Ticket assigned to agent |
| `ticket.escalated` | ticket | warning | Ticket escalated |
| `remote.session_requested` | remote_session | info | Remote assist requested |
| `remote.consent_granted` | remote_session | info | Employee granted consent |
| `remote.consent_denied` | remote_session | info | Employee denied consent |
| `remote.session_started` | remote_session | warning | Session activated |
| `remote.session_ended` | remote_session | info | Session completed |
| `admin.settings_changed` | system | warning | System settings modified |
| `admin.role_modified` | role | warning | Role permissions changed |

## Payload Sanitization

Sensitive fields are automatically redacted before storage:

```python
SENSITIVE_KEYS = {"password", "hashed_password", "secret", "token", "api_key"}
# These are replaced with "***REDACTED***" in audit payloads
```

## Consent Management

### Remote Support Consent

| Field | Description |
|-------|-------------|
| `session_id` | Which remote session |
| `employee_id` | Who is consenting |
| `consent_type` | screen_view, screen_control, file_transfer |
| `granted` | Boolean — explicit yes/no |
| `granted_at` | Timestamp of consent |
| `revoked_at` | If later revoked |
| `ip_address` | For audit trail |
| `consent_message` | Human-readable record |

### Consent Principles

1. **Explicit** — No implied consent; employee must click approve
2. **Informed** — Clear message about what access is being granted
3. **Revocable** — Employee can revoke at any time
4. **Audited** — All consent decisions are logged
5. **Time-bound** — Sessions have maximum duration limits

## Access to Audit Logs

| Role | Access Level |
|------|-------------|
| Employee | ❌ No access |
| IT Agent | ❌ No access |
| IT Lead | ❌ No access |
| IT Admin | ✅ Full read access |
| Security Auditor | ✅ Full read access (dedicated role) |

## Retention & Compliance

- Audit events are **append-only** (never modified or deleted)
- Recommended retention: 7 years for compliance
- Export capability for compliance reporting
- No PII in audit payloads beyond email/name (already known)
