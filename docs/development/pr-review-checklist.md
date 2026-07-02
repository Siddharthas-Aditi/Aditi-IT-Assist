# PR Review Checklist

For reviewers (human or AI). A PR is mergeable only when these hold. Self-review with
this list before requesting review.

## Scope & design
- [ ] Does one coherent thing; description explains what and **why**.
- [ ] Respects clean architecture (routes → services → repositories → models); no layer
      skipped, no DB in routes, no LLM outside `llm_service.py`.
- [ ] Files stay < 300 lines; single responsibility; meaningful names.
- [ ] Reuses existing services/patterns instead of duplicating.

## Correctness & safety (map to `memory/known-risks.md`)
- [ ] Grounding preserved — no cross-family KB leakage; confidence not high without grounding.
- [ ] Escalation/ticket rules intact — explicit-confirmation, idempotent, gate before handoff.
- [ ] Escalation artifacts remain immutable; no raw chat in ticket description.
- [ ] RBAC enforced in services; UI gating mirrors backend; no data-isolation leak.
- [ ] Write actions still require approval; 0 unapproved-execution guarantee intact.
- [ ] Tool/MCP calls stay within declared allow-lists and ceilings.

## Quality gates
- [ ] Lint, typecheck, and tests pass in CI.
- [ ] Meaningful tests added; relevant eval datasets pass.
- [ ] No secrets; no dummy data in product paths; no `any` / bare `type: ignore`.
- [ ] Error handling present on all I/O and external calls.

## Data & contracts
- [ ] Migration present + reversible for any schema change; contract versions bumped.
- [ ] Pydantic schemas updated (OpenAPI auto-reflects).

## Frontend
- [ ] Uses design system tokens (Aditi theme), React Query for server state, Zustand for
      client state; error boundaries at feature edges.
- [ ] Admin/support flows: breadcrumbs on deep pages, "No data" instead of `NaN%`.

## Docs & memory
- [ ] Owning `docs/**` and relevant `memory/*` updated.
- [ ] `agents/*.md` updated if agent behavior changed.
- [ ] `current-rollout-state.md` updated if flags/status changed.

## Reviewer verdict
- [ ] Approve / Request changes with specific, actionable comments.
- [ ] For risky areas, confirm the author manually traced the affected workflow.
