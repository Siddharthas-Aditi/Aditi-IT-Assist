# Playbook: Frontend & Admin Console Work

**When**: building/altering UI, especially `/dashboard/*` (admin), `/operations/*`
(agent), `/support/*` (employee), `/audit/*`.

## Approach
1. **Types** (`frontend/src/types` or feature-local) to match the backend schema.
2. **API** in `lib/api.ts` + a React Query hook in the feature's `api.ts`.
3. **Store** (Zustand) only for client state that isn't server data.
4. **Components** in `features/<area>/` composing `components/` + `components/ui`;
   admin shared bits in `components/admin/` (`Breadcrumbs`, `PageHeader`).
5. **Page** wires it together; add breadcrumbs to deep pages.
6. **Permissions**: mirror any new backend permission in `lib/permissions.ts` and gate
   the UI with `hasPermission`.
7. **Style**: Aditi theme tokens + shadcn/ui; no inline styles.

## Validate
`make lint-frontend` (ESLint `--max-warnings=0`), `make typecheck`,
`make test-frontend`. Run against a seeded backend and confirm the round trip for the
relevant role (employee/agent/lead/admin/auditor).

## Checklist
- [ ] Strict TS, no `any`; component < 300 lines; error boundary at feature edge.
- [ ] Server state via React Query; HTTP only via `lib/api.ts`.
- [ ] **Real data only** — no dummy cards; uncomputable rate → "No data", not `NaN%`.
- [ ] Breadcrumbs on deep pages; permission gating mirrors backend.
- [ ] Pure helpers in non-component files (react-refresh rule).
- [ ] Employee views never show internal notes / debug / others' data.

## Live-support UI invariants
Preserve same-window handoff + waiting state, transcript resume on refresh, typing
indicators, and queue chime/desktop notifications.

Reference: `skills/frontend/*`, `agents/dev/frontend-admin-ux.md`,
`.github/instructions/{frontend,admin-console}.instructions.md`,
`docs/product/admin-console.md`.
