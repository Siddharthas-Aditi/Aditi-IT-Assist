# Mypy Burn-down Plan

Baseline recorded 2026-08-31: **547 errors in 122 files** from
`uv run mypy app/`. This is legacy debt; UAT changes must not add to it.

## Enforcement now

- Every runtime file touched by the UAT-hardening program must pass targeted
  mypy before merge. The foundation change established this for
  `app/services/ticket_service.py`.
- CI continues to run mypy over `app/` so the total is visible. The baseline
  must only decrease; do not suppress errors with broad ignores.

## Ordered remediation

1. **Shared contracts and models** — parameterize JSON/list fields, establish
   SQLAlchemy expression types, and resolve the pgvector import boundary.
2. **Core workflow and chat services** — type workflow state, retrieval result,
   diagnostic context, and ticket/escalation contracts. This is required before
   Workstreams 1 and 2 alter routing or automation.
3. **Knowledge and ingestion** — type parser and extraction payloads behind
   stable schemas; replace untyped dictionaries at repository boundaries.
4. **API and reporting services** — type response mapping, query expressions,
   exports, and RBAC scopes.
5. **Strictness closeout** — remove obsolete ignores, add type regression
   checks for all UAT-touched modules, then set a zero-error target for `app/`.

Progress is reported with the exact `mypy app/` count in each UAT milestone.
