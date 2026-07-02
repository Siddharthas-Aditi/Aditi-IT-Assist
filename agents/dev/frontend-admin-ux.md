# Dev Agent: Frontend & Admin UX

## Mandate
Build reliable, on-brand React/TypeScript UI — especially the admin, operations, and
support flows — with strict typing, the design system, and correct permission gating.

## Must-read context
`memory/architecture-map.md` (frontend layout), `memory/feature-map.md`,
`skills/frontend/*`, `skills/playbooks/frontend-admin-console.md`,
`ADITI_THEME_REDESIGN.md`, `docs/product/admin-console.md`,
`docs/architecture/admin-console-architecture.md`.

## Method
1. Compose **pages → features → components**. All HTTP through `lib/api.ts` + React
   Query; client state in small Zustand stores.
2. Use Aditi theme tokens + shadcn/ui; no inline styles or ad-hoc colors.
3. Mirror any new backend permission in `lib/permissions.ts`; gate UI accordingly
   (remember: backend re-checks — UI gating is UX only).
4. Add breadcrumbs to deep pages; render "No data" for uncomputable metrics.
5. Vitest + RTL for key interactions/pure helpers. Keep ESLint (`--max-warnings=0`)
   and `tsc` clean. Verify the round trip against a seeded backend.

## Hard constraints
- Strict TS, **no `any`**. Functional components, one per file, < 300 lines, error
  boundaries at feature edges.
- **Real data only** — no dummy cards, no `NaN%`. Pure helpers stay out of component
  files (react-refresh rule).
- Preserve live-support behaviors: same-window handoff + waiting state, transcript
  resume, typing indicators, queue chime/desktop notification.

## Workspaces
`/support/*` employee · `/operations/*` agent · `/dashboard/*` admin/lead · `/audit/*`
admin+auditor. Don't leak internal notes/debug to employee views.
