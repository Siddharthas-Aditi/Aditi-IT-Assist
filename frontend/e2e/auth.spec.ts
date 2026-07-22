import { test, expect } from '@playwright/test';
import { EMPLOYEE } from './helpers';

/**
 * Authenticated flow — requires the backend running AND seeded team users
 * (auto-seeded on startup in development — see CLAUDE.md).
 *
 * Logging in as an employee should redirect into the /support workspace.
 */
test('employee can log in and land on the support workspace', async ({ page }) => {
  await page.goto('/login');

  await page.getByPlaceholder('you@aditiconsulting.com').fill(EMPLOYEE.email);
  await page.getByPlaceholder('••••••••').fill(EMPLOYEE.password);
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page).toHaveURL(/\/support/);
});
