# AGENTS.md — Frontend (React / TypeScript)

Scope: everything under `frontend/`. Read the root `AGENTS.md` and `CLAUDE.md` first;
this file adds frontend-local rules. Deeper context: `../memory/architecture-map.md`
(frontend layout), `../memory/feature-map.md`.

## Structure
Compose **pages → features → components**. All HTTP via `src/lib/api.ts` + React Query;
client state in small Zustand stores. Feature modules: `admin`, `agent-ops`, `chat`,
`ingestion`, `knowledge`, `specialist-chat`. Shared admin bits in `components/admin/`.

## Rules
- Strict TypeScript, **no `any`**. Functional components, one per file, < 300 lines,
  error boundary at feature edges.
- Aditi theme tokens + shadcn/ui; no inline styles / ad-hoc colors (see
  `../ADITI_THEME_REDESIGN.md`, `../skills/frontend/design-system.md`).
- Mirror backend permissions in `src/lib/permissions.ts`; gate UI accordingly (backend
  re-checks — UI gating is UX only).
- **Real data only** — no dummy cards; uncomputable rates render "No data", not `NaN%`.
- Breadcrumbs on deep pages. Pure helpers stay out of component files (react-refresh rule).
- Preserve live-support UX: same-window handoff + waiting state, transcript resume,
  typing indicators, queue chime/desktop notification.
- Employee views never show internal notes, debug traces, or other users' data.

## Working method
types → api → store → component → page → test. Vitest + RTL for key interactions and
pure helpers.

## Validate before done
`make lint-frontend` (ESLint `--max-warnings=0`), `make typecheck`, `make test-frontend`.
Verify the round trip against a seeded backend for the relevant role. Update owning
`../docs/**` when behavior changes.
