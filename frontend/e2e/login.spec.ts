import { test, expect } from '@playwright/test';

/**
 * Login page smoke tests.
 *
 * These two tests render the public /login route and do NOT require the
 * backend — they assert the page renders and validates input client-side.
 */
test.describe('Login page', () => {
  test('renders the sign-in form', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: 'Aditi IT Assist' })).toBeVisible();
    await expect(page.getByPlaceholder('you@aditiconsulting.com')).toBeVisible();
    await expect(page.getByPlaceholder('••••••••')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('shows an error for invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByPlaceholder('you@aditiconsulting.com').fill('nobody@aditi.com');
    await page.getByPlaceholder('••••••••').fill('wrong-password');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Requires the backend: an auth failure surfaces the inline error banner.
    await expect(page.getByText(/login failed|invalid|incorrect/i)).toBeVisible();
  });
});
