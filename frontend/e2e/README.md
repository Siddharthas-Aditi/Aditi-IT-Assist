# End-to-End Tests (Playwright)

Browser-driven tests for the Aditi IT Assist frontend.

## Running

```bash
# From frontend/ (Playwright auto-starts the Vite dev server on :5173)
npm run test:e2e            # headless, all tests
npm run test:e2e:ui         # interactive UI mode (watch, time-travel, pick tests)
npm run test:e2e:headed     # headed browser
npm run test:e2e:report     # open the last HTML report

# From repo root
make test-e2e
make test-e2e-ui
```

## Backend dependency

The Vite dev server proxies `/api` → backend (default `http://localhost:8000`).

- **No backend needed:** pure UI tests (e.g. login page renders).
- **Backend required + seeded:** anything that logs in or hits the API
  (`auth.spec.ts`, the invalid-credentials test). Start it with
  `make dev-infra && make dev-backend` and seed dev users
  (see CLAUDE.md → "Seeded Dev Users").

## Config

- `frontend/playwright.config.ts` — base URL, auto-start dev server, Chromium project.
- Override the target with `E2E_BASE_URL` (e.g. to point at a deployed env).
- Browsers are installed via `npx playwright install chromium` (run once per machine).

## Driving the browser with Claude

Claude Code can author and run these specs directly. For interactive
browser automation (Claude clicking through the live app), add the
Playwright MCP server: `claude mcp add playwright npx @playwright/mcp@latest`.
