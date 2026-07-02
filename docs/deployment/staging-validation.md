# Staging Validation Checklist

Run against staging after every release candidate, before production.
Staging mirrors production config (`APP_ENV=production`-style secrets, mock
flags per the rollout stage being validated).

## Boot + infrastructure
- [ ] `docker compose -f docker-compose.prod.yml up --build -d` completes;
      `migrate` exits 0; backend healthy.
- [ ] `GET /health/ready` → 200 with `database: ok`, `redis: ok`.
- [ ] Deliberately break `SECRET_KEY` → backend refuses to boot with
      `production_config_violation` (then restore).
- [ ] `GET /api/v1/health/metrics` reachable from the internal network,
      403 through the public nginx.

## Auth/session
- [ ] Login → access + refresh issued. `POST /auth/refresh` returns a NEW
      refresh token; replaying the old one → 401 `session_expired`.
- [ ] Logout → the old access token is rejected on the next call.
- [ ] A refresh token in the Authorization header cannot call any API.
- [ ] 11 rapid login attempts from one IP → 429 on the auth bucket.

## Core support flows (golden path)
- [ ] Employee chat: issue intake → grounded KB steps → tried-step
      progression → escalation offer → explicit confirm → ticket created
      once (idempotent), transcript snapshot + escalation context persisted.
- [ ] Specialist: queue notification → claim → handoff view shows summary
      first + collapsible transcript → same-window live chat, typing
      indicators both ways, idle warning → grace → auto-end.
- [ ] Admin console: users, roles (≥1 role invariant), audit log with
      before/after diffs, stats real (no NaN%).

## Remote support (mock provider stage)
- [ ] In live chat, specialist "Request remote session" → employee gets the
      consent modal (any employee page) + system message in chat.
- [ ] Deny → session `consent_denied`, audit event recorded, agent sees it.
- [ ] Grant → launch → join info returned; `connected` → `active`;
      end with resolution notes → `completed`; full event trail on the
      session; session linked to ticket AND chat session.
- [ ] Let a consent request sit 10+ min → sweeper marks it `expired`.
- [ ] Employee revoke mid-session → immediate `terminated`, audited.
- [ ] Employee cannot see another user's session (403); screen_control
      requires it_lead + justification (403 otherwise).

## Remote support (real Remote Help stage — only when flipping the flag)
- [ ] `REMOTE_SUPPORT_USE_MOCK=false` with real `REMOTE_HELP_*` creds boots.
- [ ] `GET /remote-support/provider/health` → healthy.
- [ ] Launch resolves the employee's managed device and the admin-center
      link opens the correct device blade; Remote Help session completes
      end-to-end with a real test device.
- [ ] Session correlation id (`msrh-…`) reconcilable against the M365 audit log.

## Regression gates
- [ ] Full backend suite green in CI (includes retrieval/tool/MCP/action
      safety evals: hybrid ≥ keyword, 0-unauthorized, 0-unapproved).
- [ ] Frontend lint + typecheck + vitest + build green.
- [ ] E2E (`make test-e2e`) against the staged stack.
