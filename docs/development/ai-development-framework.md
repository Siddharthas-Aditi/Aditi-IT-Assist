# AI Development Framework — How It All Fits

Aditi IT Assist ships with a project-specific operating system for AI-assisted and
human development. This is the index: what each piece is for and when to read it.

## The map

```
Operating rules (read first)
  CLAUDE.md ................ authoritative rules for Claude
  AGENTS.md ................ authoritative rules for coding agents (root + nested)
  .github/copilot-instructions.md .. repo-wide Copilot rules
  .github/instructions/*.instructions.md .. path-scoped Copilot rules

Persistent memory (load context fast)  → memory/
  project-overview · architecture-map · domain-model · feature-map
  known-risks · glossary · current-rollout-state

Process (how to do work)               → docs/development/
  engineering-workflow · commit-checklist · pr-review-checklist
  release-checklist · testing-strategy

Task playbooks (recurring how-tos)     → skills/playbooks/
  backend-api-changes · database-migrations · frontend-admin-console
  specialist-queue-flow · chat-to-ticket-handoff · live-chat-flow
  rag-and-knowledge-workflow · audit-logging · testing-and-hardening
  docs-update · code-review-self-check

Role guides (specialized dev modes)    → agents/dev/
  backend-architect · frontend-admin-ux · ai-workflow · support-workflow
  security-compliance · qa-hardening · documentation

Implementation standards (by tech)     → skills/{backend,frontend,devops,product}/
Runtime product-agent specs            → agents/0X-*.md
Deep architecture/product/security     → docs/{architecture,product,security}/
Plans / roadmap                        → plans/
Safety gates                           → scripts/, hooks/, .githooks/, .claude/settings.json
```

## How Claude should use it
1. Start a session by reading `memory/project-overview.md` + `memory/architecture-map.md`.
2. Locate the feature via `memory/feature-map.md`; read its docs + the matching
   `skills/playbooks/*` and `agents/dev/*` guide.
3. Check `memory/known-risks.md` for invariants before editing.
4. Follow `docs/development/engineering-workflow.md`; validate with
   `commit-checklist.md`; keep memory/docs updated in the same change.

## How GitHub Copilot should use it
- `.github/copilot-instructions.md` loads repo-wide. Path-scoped rules in
  `.github/instructions/*.instructions.md` apply automatically by file glob
  (backend, frontend, tests, docs, AI workflows, admin, migrations).
- Nested `AGENTS.md` in `backend/` and `frontend/` give coding agents local rules.

## What every developer does before commit
Run `docs/development/commit-checklist.md`. The Claude post-edit hook lints edited
files; the git pre-push hook gates lint + typecheck + tests. Don't bypass gates —
fix or explain.

## Maintenance
This framework is a living asset. When architecture, invariants, flags, or feature
locations change, update the relevant `memory/*` and docs in the same PR (see the
maintenance rules in `memory/README.md` and `engineering-workflow.md`).
