---
applyTo: "frontend/src/**/*.{ts,tsx}"
---
# Frontend (React / TypeScript) instructions

Apply these on top of `.github/copilot-instructions.md`.

## Architecture
- Compose: **pages → features → components**. Server state via **React Query** (all HTTP
  through `src/lib/api.ts`); client state via small **Zustand** stores.
- Strict TypeScript — **no `any`**. Functional components with hooks, one component per
  file, < 300 lines. Error boundaries at feature boundaries.

## Styling & design system
- Tailwind core utilities + shadcn/ui + Radix. Use Aditi theme tokens (see
  `skills/frontend/design-system.md` and `ADITI_THEME_REDESIGN.md`) — no inline styles,
  no ad-hoc hex colors.

## Permissions & workspaces
- Gate UI with `src/lib/permissions.ts`, which **must mirror** backend
  `core/permissions.py`. UI gating is UX only — the backend always re-checks.
- Route prefixes: `/support/*` (employee), `/operations/*` (agent), `/dashboard/*`
  (admin/lead), `/audit/*` (admin+auditor).

## Admin & support UX
- Breadcrumbs on every deep/detail/edit page (`components/admin/Breadcrumbs`).
- **Real data only** — never dummy cards. Uncomputable rates render "No data", not `NaN%`.
- Keep pure helpers out of component files (react-refresh lint rule). ESLint runs with
  `--max-warnings=0`.

## Live/support flows
- Polling-based today (chat, queue, typing). Preserve same-window handoff + waiting
  state, transcript resume on refresh, and queue chime/desktop notification behavior.

## Tests
- Vitest + RTL for key interactions and pure helpers. Keep `tsc` and ESLint clean.

Reference: `memory/feature-map.md`, `skills/playbooks/frontend-admin-console.md`,
`skills/frontend/*`, `agents/dev/frontend-admin-ux.md`.
