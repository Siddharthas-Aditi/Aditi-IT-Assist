# Team Seed + Auto-Start Seeding Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On local app start, automatically seed roles/permissions/KB and the Aditi team roster so any developer can `docker compose up` / run backend and log in with the documented accounts; the login page must list those accounts; ship the durable chat-session work + this seed UX to `main`.

**Architecture:** Keep `scripts.seed_enterprise.run_seed()` as the single idempotent seed entrypoint. Call it from FastAPI lifespan in development only (behind `SEED_ON_STARTUP`, default true in non-production). Update LoginPage + e2e helpers to the team roster. Persist support-session work from prior turn in the same push.

**Tech Stack:** FastAPI lifespan, SQLAlchemy async seed, React LoginPage, Alembic 012, docker compose.

## Global Constraints

- Do NOT auto-seed in `APP_ENV=production`.
- Seed must be idempotent (safe on every restart).
- Passwords stay overridable via `SEED_*_PASSWORD` env vars.
- Do not invent new roles; use existing `it_admin` / `it_lead` / `employee`.
- Push to `main` only after build/tests are green (user explicitly requested).

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/scripts/seed_enterprise.py` | Roster + sync passwords/roles for existing users; skip obsolete sample tickets keyed to removed emails |
| `backend/app/core/config.py` | `SEED_ON_STARTUP` setting |
| `backend/app/main.py` | Call seed after schema bootstrap in lifespan |
| `frontend/src/pages/LoginPage.tsx` | Show team roster credentials |
| `frontend/e2e/helpers.ts` (+ auth.spec if needed) | Point E2E at seeded employee |
| Support-session files from prior work | Durable chat persistence (already implemented) |
| Docs/memory | Keep seeded-user tables in sync |

---

### Task 1: Seed script hardening

**Files:** `backend/scripts/seed_enterprise.py`

- [ ] Ensure `SAMPLE_USERS` matches the team roster (already present).
- [ ] When a user already exists, update `hashed_password`, profile fields, and ensure role assignment (so restarts fix stale passwords).
- [ ] Make `seed_sample_tickets` a no-op (or rewrite to team users) — current code looks up removed emails and silently skips.
- [ ] Keep KB seed via `seed_knowledge`.

### Task 2: Auto-seed on startup

**Files:** `backend/app/core/config.py`, `backend/app/main.py`

- [ ] Add `SEED_ON_STARTUP: bool = True` (ignored / forced off when `APP_ENV=production`).
- [ ] After `create_all` in lifespan, run `scripts.seed_enterprise.run_seed()` with try/except log — never block boot on seed failure beyond logging in a way that hides schema errors (log + continue only for non-fatal seed errors; prefer fail loudly if DB unreachable).

### Task 3: Login page + E2E

**Files:** `frontend/src/pages/LoginPage.tsx`, `frontend/e2e/helpers.ts`, `frontend/e2e/auth.spec.ts`

- [ ] Replace Dev Accounts panel with the five team users (role labels + email + password).
- [ ] Click-to-fill optional UX: clicking a row fills email/password (nice DX).
- [ ] Update E2E employee credentials to `siddhartha@aditiconsulting.com` / `Siddhartha@2026`.

### Task 4: Docs sync

**Files:** `CLAUDE.md` seeded-users table, `memory/current-rollout-state.md` (if needed)

- [ ] Replace old `@aditi.com` demo users with the team roster.

### Task 5: Build, commit, push main

- [ ] Run backend unit tests + frontend typecheck/lint.
- [ ] Commit support-session + seed/login changes.
- [ ] `git push origin main`.

## Validation

1. Fresh DB / restart backend → logs show seed complete.
2. Login page lists all five users; click-fill works.
3. Login as each role lands on expected workspace.
4. KB articles present (admin Knowledge Base page or chat grounding).
5. `GET /chat/sessions` works after a chat turn (support-session work).
