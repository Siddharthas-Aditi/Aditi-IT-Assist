# Playbook: Backend API Changes

**When**: adding or changing an endpoint, service method, or repository — anything in
`backend/app/api`, `services`, or `repositories`.

## Approach
1. **Locate** the feature via `memory/feature-map.md`; read the owning service + docs.
2. **Build in order** (only the layers you need):
   - `app/schemas/*` — Pydantic v2 request/response DTO.
   - `app/repositories/*` — the DB query (all data access lives here).
   - `app/services/*` — business logic; injectable; enforce RBAC with
     `require_permissions`; emit audit events for mutations; `async`; structlog.
   - `app/api/v1/*` — thin route: validate + `Depends(service)` + delegate. Add to
     `router.py` if new.
3. **Contract**: if you change a persisted/typed contract, bump its version. Keep
   OpenAPI accurate (auto from Pydantic).
4. **Test**: `backend/tests/api` (httpx) for the endpoint, `tests/unit` for service
   logic (mock LLM/DB seams). Cover the RBAC-denied path too.
5. **Validate**: `make lint typecheck test-backend`.
6. **Docs**: update owning `docs/architecture/*` + `memory/domain-model.md` if shapes changed.

## Checklist
- [ ] No DB in the route; no LLM outside `llm_service.py`; config via `Settings`.
- [ ] RBAC enforced in the service; employee data isolation preserved.
- [ ] Error handling on all I/O; input validated by schema.
- [ ] Mutation audited; idempotency considered.
- [ ] Tests (happy + denied) added; lint/type/test green.

## Gotchas
Don't widen a response to leak internal-only fields to employees. Don't add a second
code path that duplicates an existing service — extend the service.

Reference: `skills/backend/fastapi-patterns.md`, `agents/dev/backend-architect.md`,
`.github/instructions/backend.instructions.md`.
