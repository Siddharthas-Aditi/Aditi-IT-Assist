# Commit / Pre-Push Checklist

Run before every commit (and the pre-push hook enforces the critical subset). If a
box can't be checked, fix it or explain it in the PR — don't bypass.

## Always
- [ ] Change is scoped and focused (not an unrelated grab-bag).
- [ ] `make lint` clean (backend Ruff + frontend ESLint, `--max-warnings=0`).
- [ ] `make typecheck` clean (mypy backend + tsc frontend).
- [ ] Tests for touched areas pass (`make test-backend` / `make test-frontend`).
- [ ] New/changed behavior has tests (services, workflow nodes, key UI interactions).
- [ ] No secrets, tokens, or real credentials in the diff or `.env` (only `.env.example`).
- [ ] No `any` (TS) and no `# type: ignore` without an explanatory comment.
- [ ] No commented-out code; no leftover `console.log` / stray debug prints.
- [ ] No dummy/placeholder data in product flows (see `memory/known-risks.md` #9).
- [ ] TODOs include context: `# TODO(user): why - ref`.

## If you touched the AI/agents/retrieval/tools/MCP
- [ ] Relevant eval passed: `test_retrieval_eval` / `test_tool_routing_eval` /
      `test_mcp_contract_eval` / `test_action_safety_eval`.
- [ ] Grounding/escalation/approval invariants intact (`memory/known-risks.md` #1–6).
- [ ] Matching `agents/*.md` updated if behavior changed.

## If you touched the database/schema
- [ ] Alembic migration added (next id after `009`) with a working `downgrade`.
- [ ] Typed contract versions bumped if a contract changed.
- [ ] `memory/domain-model.md` + relevant `docs/architecture/*` updated.

## If you touched RBAC / permissions
- [ ] Backend `require_permissions` enforced in the **service** layer.
- [ ] `frontend/src/lib/permissions.ts` mirrors `core/permissions.py`.
- [ ] Re-seed reminder noted if new permissions were added.

## If frontend↔backend contract changed
- [ ] TS types, `lib/api.ts`, and React Query hooks updated together.
- [ ] Round trip verified locally with seeded users.

## Docs & memory
- [ ] Owning `docs/**` doc updated.
- [ ] Relevant `memory/*` file updated (esp. `current-rollout-state.md` for flag/status changes).

## Commit message
- Imperative subject ≤ ~72 chars; body explains **why**. Reference ticket/issue.
- Suggested prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`.

_The git pre-push hook (`.githooks/pre-push`) gates on frontend lint+typecheck+vitest
and backend ruff+mypy+pytest. Bypass only intentionally with `SKIP_PREPUSH=1` /
`git push --no-verify`._
