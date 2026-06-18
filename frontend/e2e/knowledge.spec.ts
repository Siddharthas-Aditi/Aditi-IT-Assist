import { test, expect, type Page } from '@playwright/test';
import { login, ADMIN } from './helpers';

/**
 * Knowledge base authoring E2E — requires backend running + seeded.
 * Logs in as admin and exercises the article editor (happy + negative paths).
 */
test.describe('Knowledge base authoring', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN);
  });

  /** Open the blank editor, dismissing the template picker if it appears. */
  async function openBlankEditor(page: Page) {
    await page.goto('/dashboard/knowledge/new');
    const blank = page.getByRole('button', { name: /blank article/i });
    try {
      // Template picker renders once templates load; start blank if shown.
      await blank.waitFor({ state: 'visible', timeout: 5000 });
      await blank.click();
    } catch {
      // No templates configured → form is shown directly.
    }
    await expect(page.getByPlaceholder('e.g. Outlook Not Receiving Email')).toBeVisible();
  }

  test('admin can reach the article editor from the KB list', async ({ page }) => {
    await page.goto('/dashboard/knowledge');
    await expect(page.getByRole('heading', { name: 'Knowledge Base' })).toBeVisible();
    await page.getByRole('link', { name: /New Article/i }).first().click();
    await expect(page).toHaveURL(/\/dashboard\/knowledge\/new/);
  });

  test('creates a draft article (happy path)', async ({ page }) => {
    await openBlankEditor(page);
    const title = `E2E Draft Article ${Date.now()}`;

    await page.getByPlaceholder('e.g. Outlook Not Receiving Email').fill(title);
    await page.getByPlaceholder('e.g. email/outlook').fill('email/outlook');

    const save = page.getByRole('button', { name: /Save Draft/i });
    await expect(save).toBeEnabled();
    await save.click();

    // Redirects to the new article's detail page (UUID route).
    await expect(page).toHaveURL(/\/dashboard\/knowledge\/[0-9a-f-]{36}$/);
    await expect(page.getByRole('heading', { name: title, level: 1 })).toBeVisible();
  });

  // ── Negative scenarios ────────────────────────────────────────────

  test('save is blocked until both title and category are provided', async ({ page }) => {
    await openBlankEditor(page);
    const save = page.getByRole('button', { name: /Save Draft/i });

    await expect(save).toBeDisabled();
    await page.getByPlaceholder('e.g. Outlook Not Receiving Email').fill('Only a title, no category');
    await expect(save).toBeDisabled();
    await page.getByPlaceholder('e.g. email/outlook').fill('email/outlook');
    await expect(save).toBeEnabled();
  });

  test('surfaces backend validation for a too-short title', async ({ page }) => {
    await openBlankEditor(page);
    // "ab" passes the client non-empty check but violates the backend min-length(3).
    await page.getByPlaceholder('e.g. Outlook Not Receiving Email').fill('ab');
    await page.getByPlaceholder('e.g. email/outlook').fill('email/outlook');
    await page.getByRole('button', { name: /Save Draft/i }).click();

    // Should NOT navigate to a detail page, and must show a clear error.
    await expect(page.getByText(/at least 3 characters/i)).toBeVisible();
    await expect(page).toHaveURL(/\/dashboard\/knowledge\/new/);
  });
});
