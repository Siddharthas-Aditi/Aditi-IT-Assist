import { expect, type Page } from '@playwright/test';

/** Seeded dev users (see CLAUDE.md → "Seeded Dev Users"). */
export const ADMIN = { email: 'admin@aditi.com', password: 'admin123' };
export const EMPLOYEE = { email: 'alice.johnson@aditi.com', password: 'employee123' };

/** Log in through the real UI and wait until we've left the login route. */
export async function login(page: Page, creds: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByPlaceholder('you@aditi.com').fill(creds.email);
  await page.getByPlaceholder('••••••••').fill(creds.password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).not.toHaveURL(/\/login/);
}
