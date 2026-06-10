# RBAC Permission Matrix

> Authoritative role-permission reference for Aditi IT Assist enterprise platform.
> This document drives the backend permission constants, frontend helpers, and seed data.

---

## 1. Roles

| Role | Priority | Description | Default Route | Inherits From |
|------|----------|-------------|---------------|---------------|
| `employee` | 10 | Standard employee | `/support` | — |
| `security_auditor` | 15 | Read-only compliance access | `/audit` | — |
| `it_agent` | 20 | IT support specialist | `/operations` | — |
| `it_lead` | 30 | IT team lead | `/dashboard` | `it_agent` |
| `it_admin` | 40 | Full administrative control | `/dashboard` | `it_lead` |

> **Inheritance** means the higher role receives all permissions of the lower role
> plus its own additional grants.

---

## 2. Resources, Actions & Scopes

### Scope Definitions

| Scope | Meaning | Example |
|-------|---------|---------|
| `own` | Resources belonging to the current user | Employee's own tickets |
| `assigned` | Resources assigned to the current user | Agent's assigned tickets |
| `team` | Resources within the user's team/queue | Lead's team tickets |
| `all` | Every resource of this type system-wide | Admin viewing all data |

---

## 3. Complete Permission Matrix

### 3.1 Tickets

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `ticket:create` | Create | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `ticket:read_own` | Read | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `ticket:read_assigned` | Read | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `ticket:read_team` | Read | team | ❌ | ❌ | ✅ | ✅ | ❌ | — | — |
| `ticket:read_all` | Read | all | ❌ | ❌ | ❌ | ✅ | ✅ | — | — |
| `ticket:update_assigned` | Update | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:update_all` | Update | all | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:assign` | Assign | team | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:reassign` | Reassign | all | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:escalate` | Escalate | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:close` | Close | team | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:reopen` | Reopen | own | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:delete` | Delete | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `ticket:add_comment` | Comment | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `ticket:add_internal_note` | Internal Note | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `ticket:view_internal_notes` | Read Internal | assigned | ❌ | ✅ | ✅ | ✅ | ✅ | — | — |
| `ticket:bulk_update` | Bulk Update | team | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `ticket:export` | Export | all | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |

### 3.2 Chat / Live Support

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `chat:start` | Start | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `chat:read_own` | Read | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `chat:read_assigned` | Read | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `chat:read_all` | Read | all | ❌ | ❌ | ✅ | ✅ | ❌ | — | — |
| `chat:accept_handoff` | Accept | team | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `chat:transfer` | Transfer | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `chat:end_session` | End | assigned | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `chat:request_live_agent` | Request Agent | own | ✅ | ❌ | ❌ | ❌ | ❌ | — | — |

### 3.3 Remote Support

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `remote:request_view` | Request View | — | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `remote:request_control` | Request Control | — | ❌ | ❌ | ✅ | ✅ | ❌ | 🔴 | — |
| `remote:grant_consent` | Grant Consent | own | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| `remote:revoke_consent` | Revoke Consent | own | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | — |
| `remote:start_session` | Start Session | — | ❌ | ✅ | ✅ | ✅ | ❌ | 🔴 | — |
| `remote:end_session` | End Session | — | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | — |
| `remote:read_own_sessions` | Read Own | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `remote:read_all_sessions` | Read All | all | ❌ | ❌ | ✅ | ✅ | ✅ | — | — |

### 3.4 Knowledge Base

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `knowledge:read` | Read | all | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `knowledge:create` | Create Draft | — | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `knowledge:update_own` | Update | own | ❌ | ✅ | ✅ | ✅ | ❌ | — | — |
| `knowledge:update_all` | Update Any | all | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `knowledge:approve` | Approve/Publish | all | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| `knowledge:delete` | Delete | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `knowledge:manage_categories` | Manage Categories | all | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | — |

### 3.5 Analytics & Reporting

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `analytics:view_own` | View Own Stats | own | ✅ | ✅ | ✅ | ✅ | ❌ | — | — |
| `analytics:view_team` | View Team | team | ❌ | ❌ | ✅ | ✅ | ❌ | — | — |
| `analytics:view_all` | View Global | all | ❌ | ❌ | ✅ | ✅ | ✅ | — | — |
| `analytics:export` | Export Reports | all | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | — |
| `analytics:view_agent_perf` | Agent Performance | team | ❌ | ❌ | ✅ | ✅ | ❌ | — | — |

### 3.6 Administration

| Code | Action | Scope | Employee | Agent | Lead | Admin | Auditor | Audit | Consent |
|------|--------|-------|----------|-------|------|-------|---------|-------|---------|
| `admin:manage_users` | CRUD Users | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `admin:manage_roles` | CRUD Roles | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `admin:assign_roles` | Assign Roles | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `admin:manage_groups` | CRUD Groups | all | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | — |
| `admin:manage_settings` | System Settings | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `admin:manage_integrations` | Integrations | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | — |
| `admin:manage_sla_policies` | SLA Policies | all | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | — |
| `admin:view_audit_log` | Read Audit | all | ❌ | ❌ | ❌ | ✅ | ✅ | — | — |
| `admin:export_audit_log` | Export Audit | all | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | — |
| `admin:impersonate_user` | Impersonate | all | ❌ | ❌ | ❌ | ✅ | ❌ | 🔴 | ✅ |

---

## 4. High-Risk Actions (🔴 — Mandatory Audit)

These actions always produce a `severity: critical` audit event:

| Action | Justification |
|--------|---------------|
| `ticket:delete` | Permanent data loss |
| `remote:request_control` | Direct access to employee machine |
| `remote:start_session` | Activates live remote connection |
| `admin:manage_users` | Identity mutation |
| `admin:manage_roles` | Privilege escalation vector |
| `admin:assign_roles` | Privilege escalation vector |
| `admin:manage_settings` | System-wide impact |
| `admin:manage_integrations` | External system access |
| `admin:impersonate_user` | Full identity assumption |
| `knowledge:delete` | Knowledge loss |

---

## 5. Consent-Required Actions (✅ Consent column)

These actions require explicit user consent before execution:

| Action | Who Consents | Consent Type |
|--------|--------------|--------------|
| `remote:grant_consent` | Employee | screen_view / screen_control |
| `admin:impersonate_user` | Target user (if attended) | impersonation |

---

## 6. UI Route Access Matrix

| Route Pattern | Employee | Agent | Lead | Admin | Auditor |
|---------------|----------|-------|------|-------|---------|
| `/support/*` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/support/chat` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/support/tickets` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/support/profile` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `/operations/*` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/operations/queue` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/operations/assigned` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/operations/remote-assist` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/dashboard/*` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/dashboard/team-queue` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/dashboard/knowledge` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/dashboard/users` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `/audit` | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## 7. UI Component Visibility

| Component | Permission Required |
|-----------|-------------------|
| "New Support Chat" button | `chat:start` |
| "My Tickets" tab | `ticket:read_own` |
| "All Tickets" / Queue view | `ticket:read_assigned` |
| "Assign" action on ticket | `ticket:assign` |
| "Close" action on ticket | `ticket:close` |
| Internal notes section | `ticket:view_internal_notes` |
| "Request Remote Session" | `remote:request_view` |
| Remote consent modal | `remote:grant_consent` |
| Analytics dashboard | `analytics:view_team` |
| Agent performance panel | `analytics:view_agent_perf` |
| User management page | `admin:manage_users` |
| Audit log viewer | `admin:view_audit_log` |
| Knowledge approve button | `knowledge:approve` |
| "Export" buttons | `analytics:export` or `ticket:export` |

---

## 8. API Endpoint → Permission Mapping

| Method | Endpoint | Required Permission(s) |
|--------|----------|----------------------|
| POST | `/auth/login` | (public) |
| POST | `/auth/register` | (public in dev / `admin:manage_users` in prod) |
| GET | `/auth/me` | (any authenticated) |
| POST | `/tickets` | `ticket:create` |
| GET | `/tickets/my` | `ticket:read_own` |
| GET | `/tickets/queue` | `ticket:read_assigned` |
| POST | `/tickets/:id/assign` | `ticket:assign` |
| POST | `/tickets/:id/status` | `ticket:update_assigned` |
| POST | `/tickets/:id/comments` | `ticket:add_comment` or `ticket:add_internal_note` |
| GET | `/analytics/dashboard` | `analytics:view_team` |
| GET | `/analytics/workload` | `analytics:view_team` |
| POST | `/remote-support/request` | `remote:request_view` |
| POST | `/remote-support/:id/consent` | `remote:grant_consent` |
| POST | `/remote-support/:id/start` | `remote:start_session` |
| POST | `/remote-support/:id/end` | `remote:end_session` |
| GET | `/admin/audit-log` | `admin:view_audit_log` |
| POST | `/admin/users` | `admin:manage_users` |
| PUT | `/admin/users/:id/roles` | `admin:assign_roles` |

---

## 9. Seeded Users (Local Dev Only)

| User | Email | Password | Role |
|------|-------|----------|------|
| Alice Johnson | alice.johnson@aditi.com | employee123 | employee |
| Bob Williams | bob.williams@aditi.com | employee123 | employee |
| Charlie Martinez | charlie.agent@aditi.com | agent123 | it_agent |
| Diana Chen | diana.agent@aditi.com | agent123 | it_agent |
| Edward Thompson | edward.lead@aditi.com | lead123 | it_lead |
| System Administrator | admin@aditi.com | admin123 | it_admin |
| Frank Auditor | auditor@aditi.com | auditor123 | security_auditor |

⚠️ **These credentials are for local development ONLY. Never use in production.**

---

## 10. Implementation References

| Artifact | Path |
|----------|------|
| Backend permission constants | `backend/app/core/permissions.py` |
| Frontend permission helpers | `frontend/src/lib/permissions.ts` |
| Seed data & role mappings | `backend/scripts/seed_enterprise.py` |
| Auth dependencies / guards | `backend/app/services/auth/dependencies.py` |
| Route guards (React) | `frontend/src/components/RouteGuard.tsx` |
