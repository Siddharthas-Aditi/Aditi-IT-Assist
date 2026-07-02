# Playbook: Docs & Memory Update

**When**: any change that alters architecture, a domain invariant, a feature's location,
a risk, or flag/rollout state. (Repo policy: every new feature needs a doc update.)

## What to update, in the same PR
1. **Owning doc** in `docs/{architecture,product,security,development}/`.
2. **Memory**: the relevant `memory/*` file. Specifically:
   - Architecture/flow change → `memory/architecture-map.md`.
   - Entity/schema/invariant change → `memory/domain-model.md`.
   - New/moved feature → `memory/feature-map.md`.
   - New risky area/invariant → `memory/known-risks.md`.
   - New term → `memory/glossary.md`.
   - Flag/status/phase change → `memory/current-rollout-state.md` **and** the `CLAUDE.md`
     implementation-status table.
3. **Agent behavior** change → the matching `agents/0X-*.md`.
4. New recurring how-to → `skills/playbooks/*`; new tech pattern →
   `skills/{backend,frontend,devops,product}/*`.

## Principles
Progressive disclosure — keep `CLAUDE.md`/`AGENTS.md` concise and link to depth. State a
fact once and link to it. Prose over bullet walls. Concrete file paths. If two docs
disagree, verify against code, fix the wrong one. Don't let memory drift from reality.

## Checklist
- [ ] Owning doc updated.
- [ ] Correct `memory/*` file(s) updated.
- [ ] `current-rollout-state.md` + `CLAUDE.md` table updated for flag/status changes.
- [ ] `agents/*.md` updated if behavior changed.
- [ ] No duplicated source of truth introduced.
