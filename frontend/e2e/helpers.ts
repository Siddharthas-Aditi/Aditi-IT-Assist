import { expect, type Page } from '@playwright/test';

/** Seeded team roster (see CLAUDE.md → "Seeded Dev Users"). */
export const ADMIN = {
  email: 'hareesh@aditiconsulting.com',
  password: 'Hareesh@2026',
};
export const EMPLOYEE = {
  email: 'siddhartha@aditiconsulting.com',
  password: 'Siddhartha@2026',
};

/** Log in through the real UI and wait until we've left the login route. */
export async function login(page: Page, creds: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByPlaceholder('you@aditiconsulting.com').fill(creds.email);
  await page.getByPlaceholder('••••••••').fill(creds.password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).not.toHaveURL(/\/login/);
}
