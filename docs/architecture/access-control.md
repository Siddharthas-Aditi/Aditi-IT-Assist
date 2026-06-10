# Access Control Architecture

> Enterprise RBAC model for Aditi IT Assist platform.

## Role Hierarchy

```
it_admin (priority: 40) — Full system access
    └── it_lead (priority: 30) — Team management + analytics
        └── it_agent (priority: 20) — Ticket operations + live support
            └── employee (priority: 10) — Self-service access

security_auditor (priority: 15) — Read-only audit/compliance access
```

## Permission Matrix

| Permission Code | Employee | IT Agent | IT Lead | IT Admin | Auditor |
|----------------|----------|----------|---------|----------|---------|
| `ticket:create` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `ticket:view_own` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `ticket:view_all` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `ticket:update` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `ticket:assign` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `ticket:escalate` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `ticket:close` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `ticket:add_internal_note` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `chat:start` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `chat:view_own` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `chat:view_all` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `chat:accept_handoff` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `remote:request_view` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `remote:request_control` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `remote:approve_consent` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `remote:view_sessions` | ❌ | ❌ | ❌ | ✅ | ✅ |
| `knowledge:view` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `knowledge:create` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `knowledge:approve` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `knowledge:manage` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `analytics:view_team` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `analytics:view_all` | ❌ | ❌ | ✅ | ✅ | ✅ |
| `analytics:export` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `admin:manage_users` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `admin:manage_roles` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `admin:manage_settings` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `admin:view_audit` | ❌ | ❌ | ❌ | ✅ | ✅ |
| `admin:manage_integrations` | ❌ | ❌ | ❌ | ✅ | ❌ |

## Enforcement Points

### Backend (API Layer)
- FastAPI dependencies check roles/permissions per endpoint
- `require_roles()` — checks if user has any of specified roles
- `require_permissions()` — checks if user has all specified permissions
- Ticket queries filtered by `requester_id` for employees

### Frontend (UI Layer)
- `RouteGuard` component blocks unauthorized route access
- `useAuthStore().hasRole()` for conditional UI rendering
- Sidebar navigation differs per role
- Role-aware home redirect after login

## Data Isolation Rules

1. **Employees** see ONLY their own tickets, chats, and profile
2. **IT Agents** see all tickets but cannot access admin functions
3. **Internal notes** on tickets are hidden from employees
4. **Audit logs** are read-only for security auditors
5. **Remote session consent** can only be granted by the employee themselves
