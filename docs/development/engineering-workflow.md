# Engineering Workflow (AI-Assisted & Human)

The standard process for all development in Aditi IT Assist — whether driven by
Claude, GitHub Copilot, or a human. It exists to keep changes **planned, iterative,
validated, documented, and safe**. Treat prompts, retrieval rules, playbooks, schemas,
and workflows as production assets.

## 0. Load context (start of every session)
1. Read `memory/project-overview.md`, `memory/architecture-map.md`, and the memory
   files relevant to your area (`domain-model`, `feature-map`, `known-risks`).
2. Read the root `CLAUDE.md` / `AGENTS.md` operating rules.
3. Use `memory/feature-map.md` to find the exact files + docs for the feature.
4. Read the relevant `docs/architecture/*` and `skills/playbooks/*` for the task.

## 1. Clarify scope
- State what will change, which layer(s) and which feature(s) are affected, and which
  invariants in `memory/known-risks.md` are in play. If ambiguous, ask before coding.

## 2. Plan
- Write a short plan: files to touch, order, tests to add, docs/memory to update,
  rollback story. For multi-step work, track it as a task list.
- Non-trivial or cross-cutting work gets a `plans/*.md` entry.

## 3. Implement iteratively (small batches)
- Backend order: **model → schema → repository → service → route → test**.
- Frontend order: **types → api → store → component → page → test**.
- Never skip a layer (no DB in routes, no LLM outside `llm_service.py`, config via
  `Settings`). Keep files < 300 lines. No `any` in TS. Async for I/O.
- **No dummy data in product flows** — real integrations; unknowns render "No data".
- Make focused commits; don't ship one giant patch.

## 4. Validate before claiming done (see `commit-checklist.md`)
- `make lint` and `make typecheck` clean.
- `make test-backend` / `make test-frontend` for touched areas; full `make test` for
  cross-cutting changes. Add tests with every meaningful change.
- Run the relevant **eval dataset** if you touched agents/tools/MCP/retrieval
  (`backend/tests/data/*.yaml` + their `test_*_eval.py`).
- Manually trace the affected workflow (chat → escalation → handoff, queue claim, etc.).
- Verify frontend↔backend contract (permission gating mirrors backend; API shapes match).

## 5. Schema / DB changes (safe path)
- Add an Alembic migration (`make db-revision MSG=...`), next id after `009`.
- Provide a working `downgrade`. Bump any typed contract version you change.
- Update `memory/domain-model.md` + the relevant `docs/architecture/*`.
- See `skills/playbooks/database-migrations.md`.

## 6. Frontend↔backend integrated changes
- Change backend contract → regenerate/adjust TS types → update `lib/api.ts` → update
  React Query hooks → update components → mirror any new permission in `lib/permissions.ts`.
- Validate the round trip locally (seeded users, real API), not just unit tests.

## 7. Document
- Update the owning `docs/**` doc, the relevant `memory/*` file, and — if you changed
  flag/rollout state — `memory/current-rollout-state.md` and the `CLAUDE.md` status table.
- Agent behavior change → update the matching `agents/*.md`.

## 8. Prepare the change for review
- Fill the PR template. Summarize what/why, layers touched, tests + evals run, docs
  updated, risk areas, rollback. Run `pr-review-checklist.md` on yourself first.

## Handling blockers
- If blocked (missing infra, failing unrelated test, ambiguous requirement, a change
  that would break a `known-risks` invariant): **stop, don't hack around it.** Report
  the blocker, the options, and a recommendation. Never disable a safety gate,
  fabricate data, or `# type: ignore` without an explanatory comment to get green.

## Avoiding context drift
- Re-read `memory/` when resuming a long task. Keep edits scoped to the plan. If the
  plan changes, update it before continuing. Prefer verifying against the code over
  trusting stale memory — and fix the memory file when they disagree.
