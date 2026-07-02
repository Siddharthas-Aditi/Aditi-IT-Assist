# Playbook: Code-Review Self-Check

**When**: before you commit or open a PR. Fast final pass to catch the common failures.
Full lists: `docs/development/commit-checklist.md`, `pr-review-checklist.md`.

## 60-second scan
1. **Scope** — does this diff do one coherent thing? Remove anything unrelated.
2. **Layers** — no DB in routes, no LLM outside `llm_service.py`, service layer not
   bypassed, files < 300 lines.
3. **Safety** (map to `memory/known-risks.md`) — grounding preserved? escalation/ticket
   rules intact? RBAC enforced in services + mirrored in `lib/permissions.ts`? write
   actions still approval-gated? artifacts still immutable?
4. **Quality** — lint/typecheck/tests green; tests added; relevant eval passed; no
   `any`, no bare `# type: ignore`, no `console.log`/debug prints, no commented-out code.
5. **Data** — no secrets in diff/`.env`; **no dummy data in product flows** ("No data"
   not `NaN%`); migration reversible; contract versions bumped.
6. **Docs** — owning doc + `memory/*` updated; `current-rollout-state.md` if flags changed.

## Then
- Run `make lint typecheck test` (or the touched-area subset).
- Fill the PR template: what/why, layers, tests+evals run, docs updated, risks, rollback.
- For sensitive diffs, consider `/security-review`.

If any item fails, fix it or explain it in the PR — **don't bypass a gate to go green.**
