import { test, expect } from '@playwright/test';

/**
 * Authenticated flow — requires the backend running AND seeded dev users
 * (see CLAUDE.md → "Seeded Dev Users" / Environment Setup).
 *
 * Logging in as an employee should redirect into the /support workspace.
 */
test('employee can log in and land on the support workspace', async ({ page }) => {
  await page.goto('/login');

  await page.getByPlaceholder('you@aditi.com').fill('alice.johnson@aditi.com');
  await page.getByPlaceholder('••••••••').fill('employee123');
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page).toHaveURL(/\/support/);
});
