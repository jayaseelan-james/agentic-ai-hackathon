import { test, expect } from '@playwright/test';
import path from 'node:path';

// Speech has separate coverage; these fixtures deliberately omit speech routes.
test.beforeEach(async ({context}) => {
  await context.addInitScript(() => { try { localStorage.setItem('autosage-speech-muted', 'true'); } catch { /* about:blank has no storage origin. */ } });
});

const label = 'Check what’s wrong with my car';

for (const mode of ['general', 'bmw_g20']) {
  test(`${mode}: one click starts a sensor review, polls its reply, and can check again`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    let chat: any = null;
    let creations = 0;
    let checks = 0;
    const message = (role: string, text: string, state = 'complete') => ({
      id: `${role}-${checks}`, role, text, state, attachments: [], activity: [], citations: [],
      search_suggestions: [], diagnostic_inference: [], follow_up_question: null, report: null,
    });
    await page.route('**/api/**', async route => {
      const req = route.request();
      const pathname = new URL(req.url()).pathname;
      if (pathname === '/api/health') return route.fulfill({ json: { configured: true, provider: 'gemini' } });
      if (pathname === '/api/incidents' && req.method() === 'GET') return route.fulfill({ json: chat ? [chat] : [] });
      if (pathname === '/api/incidents' && req.method() === 'POST') {
        const body = req.postDataJSON();
        expect(body.mode || 'general').toBe(mode);
        creations++;
        chat = { id: 'sensor-chat', mode, title: 'New chat', vehicle: body.vehicle || {}, messages: [], safety: null };
        return route.fulfill({ status: 201, json: chat });
      }
      if (pathname.endsWith('/messages')) {
        expect(req.postData()).toContain('name="sensor_check"\r\n\r\ntrue');
        expect(req.postData()).toContain('available sensor readings and recorded history');
        checks++;
        chat.messages.push(message('user', label), message('assistant', '', 'processing'));
        return route.fulfill({ status: 202, json: chat });
      }
      if (pathname.endsWith('/sensor-chat')) {
        const answer = chat.messages.at(-1);
        answer.state = 'complete';
        answer.text = 'The rear-left tire reads 1.8 bar and has fallen from 2.3 bar in the recorded history. Compare with the vehicle reference while safely parked; the cause remains unconfirmed.';
        answer.activity = [{ id: `read-${checks}`, tool: 'read_vehicle_sensors', initiator: 'backend', status: 'complete', summary: 'Automatic sensor check', timestamp: new Date().toISOString() }];
        return route.fulfill({ json: chat });
      }
      return route.fulfill({ status: 404, json: { detail: 'Unexpected request' } });
    });

    await page.goto(mode === 'general' ? '/' : '/bmw');
    await expect(page).toHaveTitle(mode === 'general' ? 'AutoSage' : 'AutoSage · BMW 330i G20');
    await expect(page.getByRole('heading', { name: /What’s happening with your/ })).toBeVisible();
    const button = page.getByRole('button', { name: label, exact: true });
    await expect(button).toBeEnabled();
    await expect(page.locator('vite-error-overlay')).toHaveCount(0);
    if (process.env.QA_SCREENSHOT_DIR && mode === 'general') await page.screenshot({ path: path.join(process.env.QA_SCREENSHOT_DIR, 'sensor-check-desktop.png') });
    await button.click();
    await expect(button).toBeDisabled();
    await expect(page.getByText('Analyzing the problem…')).toBeVisible();
    await expect(page.getByText(/The rear-left tire reads 1.8 bar/)).toBeVisible();
    await expect(button).toBeEnabled();
    expect(creations).toBe(1);
    expect(checks).toBe(1);
    // Keep the same conversation, without typing or creating another chat.
    await button.click();
    await expect(page.getByText(/The rear-left tire reads 1.8 bar/)).toHaveCount(2);
    expect(creations).toBe(1);
    expect(checks).toBe(2);
    if (process.env.QA_SCREENSHOT_DIR && mode === 'general') await page.screenshot({ path: path.join(process.env.QA_SCREENSHOT_DIR, 'sensor-check-result.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(button).toBeVisible();
    await expect(button).toBeInViewport();
    await expect.poll(async () => {
      const box = await page.locator('.sidebar').boundingBox();
      return box ? box.x + box.width : 0;
    }).toBeLessThanOrEqual(1);
    await expect(page.getByRole('textbox', { name: 'Message' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (process.env.QA_SCREENSHOT_DIR && mode === 'general') await page.screenshot({ path: path.join(process.env.QA_SCREENSHOT_DIR, 'sensor-check-mobile.png'), animations: 'disabled' });
    expect(errors).toEqual([]);
  });
}

test('disabled readings show an immediate reply and leave chat usable', async ({ page }) => {
  const chat = { id: 'disabled', mode: 'general', title: 'Existing chat', vehicle: {}, messages: [] as any[], safety: null };
  await page.route('**/api/**', async route => {
    const req = route.request();
    if (req.url().endsWith('/health')) return route.fulfill({ json: { configured: false } });
    if (req.url().endsWith('/incidents')) return route.fulfill({ json: [chat] });
    chat.messages = [{ id: 'status', role: 'assistant', text: 'Sensor readings are not enabled, so I could not check your car. Enable vehicle readings and try again, or describe the warning or symptom in chat.', state: 'complete', attachments: [], activity: [], citations: [], search_suggestions: [], diagnostic_inference: [], follow_up_question: null }];
    return route.fulfill({ status: 202, json: chat });
  });
  await page.goto('/');
  await page.getByRole('button', { name: label, exact: true }).click();
  await expect(page.getByText(/Sensor readings are not enabled/)).toBeVisible();
  await expect(page.getByRole('button', { name: label, exact: true })).toBeEnabled();
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeEnabled();
});
