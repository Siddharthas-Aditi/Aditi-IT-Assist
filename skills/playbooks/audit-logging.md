# Playbook: Audit Logging

**When**: adding or changing any state-mutating action (role/user changes, KB
transitions, ticket/specialist-chat transitions, tool calls, config changes).

## Key files
`services/audit_service.py`, `models/audit.py`. Tool-call auditing:
`services/agents/tools/runtime.py` (records `args_hash`/`result_hash`). Docs:
`docs/security/consent-and-audit.md`.

## Approach
1. Emit an `AuditEvent` from the **service** performing the mutation, with:
   actor, action, target, and a **before/after diff** where state changes.
2. Audit **every path** for governed actions — including **rejections/denials**
   (allow-list, RBAC, approval). The runtime already does this; match that discipline.
3. Never log secrets or full sensitive payloads — use hashes/references
   (`args_hash`, `result_hash`, `auth_secret_ref`).
4. Audit records are **immutable** — no update/delete path.
5. Access to audit logs is restricted to `it_admin` / `security_auditor`.

## Validate
Unit-test that the mutation emits the expected event (actor, action, diff), including
the denied path. `make test-backend`.

## Checklist
- [ ] Mutation emits an audit event with before/after.
- [ ] Denials/rejections audited too.
- [ ] No secrets in the log; hashes/refs used.
- [ ] Audit read access RBAC-restricted; records immutable.

Reference: `agents/dev/security-compliance.md`.
