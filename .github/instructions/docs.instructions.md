---
applyTo: "{docs,memory,plans,agents,skills}/**/*.md"
---
# Documentation & memory instructions

Docs and memory are versioned production assets, kept in lockstep with code.

- **Progressive disclosure**: `CLAUDE.md` / `AGENTS.md` stay concise and point to deeper
  docs. Put durable knowledge in `memory/` and `docs/`, not in the root files.
- **Single source of truth**: describe a fact once and link to it; don't duplicate across
  files. If two docs disagree, the code wins — fix the doc.
- **Update in the same PR** as the code: owning `docs/**` doc, the relevant `memory/*`
  file, and (for flag/status changes) `memory/current-rollout-state.md` + the `CLAUDE.md`
  status table. Agent behavior change → the matching `agents/*.md`.
- **Style**: prose over walls of bullets; concrete file paths; short and actionable.
  Keep examples runnable. Note versions/flags where relevant.
- New recurring how-to → add a `skills/playbooks/*` file. New tech pattern →
  `skills/{backend,frontend,devops,product}/*`. New role guide → `agents/dev/*`.

Reference: `docs/development/docs-update` guidance in
`skills/playbooks/docs-update.md`, and `memory/README.md` maintenance rules.
