import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E configuration for Aditi IT Assist frontend.
 *
 * - Tests live in ./e2e and drive the app through a real browser.
 * - `webServer` auto-starts the Vite dev server (port 5173) before the suite
 *   and reuses an already-running one locally.
 * - The Vite dev server proxies `/api` to the backend (VITE_API_TARGET,
 *   default http://localhost:8000). Tests that log in or hit the API therefore
 *   require the backend to be running and seeded (see CLAUDE.md → Environment Setup).
 *   Pure UI tests (e.g. login page rendering) work without the backend.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['list']] : 'list',

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: process.env.E2E_BASE_URL || 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
