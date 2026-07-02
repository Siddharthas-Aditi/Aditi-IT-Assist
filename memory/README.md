# memory/ — Persistent Project Memory

Continuity docs for AI coding sessions (Claude, Copilot) and new human contributors.
Read these **first** at the start of a session to load context quickly, without
re-deriving it from source every time.

`CLAUDE.md` and `AGENTS.md` remain the authoritative operating instructions. This
directory is the **stable, slower-changing knowledge base** they point to
(progressive disclosure). When something here conflicts with the code, the code wins —
fix the memory file in the same change.

## Files

| File | Purpose | Read when |
|------|---------|-----------|
| `project-overview.md` | Mission, users, what the product does | Every new session |
| `architecture-map.md` | Layers, key dirs, request/data flow, where things live | Before any non-trivial change |
| `domain-model.md` | Core entities, relationships, lifecycles, invariants | Touching models/schemas/DB |
| `feature-map.md` | Feature → owning code + docs, so you find the right files fast | Locating a feature |
| `known-risks.md` | Dangerous-to-change areas, invariants that must not break | Before editing sensitive code |
| `glossary.md` | Business + system terms | Anytime a term is unclear |
| `current-rollout-state.md` | What's shipped, behind flags, stubbed, or deferred | Planning new work |

## Maintenance rule

Any change that alters architecture, a domain invariant, a feature's location, a
risk, or rollout/flag state **must update the relevant memory file in the same PR**.
Treat these as versioned production assets, not scratch notes. See
`docs/development/engineering-workflow.md`.
