import { test, expect } from '@playwright/test';
import { login, EMPLOYEE } from './helpers';

/**
 * Support chat E2E — requires backend running + seeded.
 * Runs against the keyword-fallback agent when no LLM key is configured,
 * so assertions check the round-trip and UI behaviour, not exact wording.
 */
test.describe('Support chat', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, EMPLOYEE);
    await page.goto('/support/chat');
    await expect(page.getByRole('heading', { name: 'Aditi IT Support Assistant' })).toBeVisible();
  });

  test('shows the welcome message on load', async ({ page }) => {
    await expect(page.getByText(/I'm the Aditi IT Support Assistant/i)).toBeVisible();
  });

  test('responds to a described IT issue (happy path)', async ({ page }) => {
    const input = page.getByPlaceholder('Describe your IT issue…');
    const issue = 'My Outlook is not receiving any new emails since this morning';

    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/chat/message') && r.request().method() === 'POST',
    );
    await input.fill(issue);
    await input.press('Enter');

    const resp = await respPromise;
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect((body.content ?? '').length).toBeGreaterThan(0);

    // User message echoed, input cleared after send.
    await expect(page.getByText(issue)).toBeVisible();
    await expect(input).toHaveValue('');
  });

  // ── Negative scenarios ────────────────────────────────────────────

  test('send is disabled for empty and whitespace-only input', async ({ page }) => {
    const input = page.getByPlaceholder('Describe your IT issue…');
    const send = page.getByRole('button', { name: 'Send message' });

    await expect(send).toBeDisabled();
    await input.fill('     ');
    await expect(send).toBeDisabled();
    await input.fill('hello');
    await expect(send).toBeEnabled();
  });

  test('caps very long input at the backend limit (5000 chars)', async ({ page }) => {
    const input = page.getByPlaceholder('Describe your IT issue…');
    await input.fill('x'.repeat(6000));
    const len = await input.evaluate((el) => (el as HTMLInputElement).value.length);
    expect(len).toBe(5000);
  });

  test('handles gibberish gracefully without crashing', async ({ page }) => {
    const input = page.getByPlaceholder('Describe your IT issue…');
    const respPromise = page.waitForResponse((r) => r.url().includes('/chat/message'));

    await input.fill('asdkjh qwoieu zxcmnzxc fjdksla');
    await input.press('Enter');

    const resp = await respPromise;
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    // Agent should still reply with *something* (clarification or escalation).
    expect((body.content ?? '').length).toBeGreaterThan(0);
  });
});
