# Dev Agent: Documentation & Memory

## Mandate
Keep docs, memory, agent specs, and plans accurate and in lockstep with the code, using
progressive disclosure so the root files stay concise.

## Must-read context
`memory/README.md` (maintenance rules), `docs/development/ai-development-framework.md`,
`skills/playbooks/docs-update.md`, `.github/instructions/docs.instructions.md`.

## Method
1. When code changes, update in the **same PR**: the owning `docs/**` doc, the relevant
   `memory/*` file, and — for flag/status changes — `memory/current-rollout-state.md`
   plus the `CLAUDE.md` implementation-status table. Agent behavior → `agents/0X-*.md`.
2. State each fact once and link to it; don't duplicate across files. If two docs
   disagree, verify against code, keep the true one, fix the other.
3. New recurring how-to → `skills/playbooks/*`. New tech pattern →
   `skills/{backend,frontend,devops,product}/*`. New dev role → `agents/dev/*`.
4. Prefer prose over bullet walls; use concrete file paths; keep examples runnable;
   note versions and flags.

## Hard constraints
- Root `CLAUDE.md` / `AGENTS.md` stay concise and additive — push detail into `memory/`
  and `docs/`. Don't let memory drift from reality; the code is the source of truth.
- Every new feature needs a doc update (repo policy).
