import { test, expect } from '@playwright/test';
import path from 'node:path';

// Speech has separate coverage; keep these fixtures focused on connectivity.
test.beforeEach(async ({context}) => {
  await context.addInitScript(() => { try { localStorage.setItem('autosage-speech-muted', 'true'); } catch { /* about:blank has no storage origin. */ } });
});

for (const width of [1280, 390]) {
  test(`remote breakdown toggle selects hosted Gemma and blocks web access at ${width}px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    const external: string[] = [];
    context.on('page', p => {
      p.on('pageerror', e => errors.push(e.message));
      p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    });
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    context.on('request', req => { if (/^https?:/.test(req.url()) && !['127.0.0.1', 'localhost'].includes(new URL(req.url()).hostname)) external.push(req.url()); });
    const now = new Date().toISOString();
    const state = {
      enabled: false, internet_blocked: false, source: 'simulated', fixture_id: 'demo-sensors-v1', revision: 0, snapshot_time: now,
      groups: { Tires: ['tpms_rear_left_bar'] }, scenarios: [{ id: 'tire_pressure_loss', label: 'Tire pressure loss', description: 'Pressure falls.' }],
      channels: { tpms_rear_left_bar: { name: 'tpms_rear_left_bar', label: 'Rear-left tire', unit: 'bar', value: 1.8, available: true, scenario: 'tire_pressure_loss', lookback_minutes: 1440, samples: [{ timestamp: now, value: 1.8 }], limits: { min: 0, max: 10 } } },
    };
    let chat: any = null;
    await context.route('**/api/**', async route => {
      const req = route.request();
      const url = new URL(req.url()).pathname;
      if (url === '/api/health') return route.fulfill({ json: { configured: true, verified: false, provider: state.internet_blocked ? 'gemma' : 'gemini', model: state.internet_blocked ? 'gemma-4-26b-a4b-it' : 'gemini-test', internet_blocked: state.internet_blocked, web_search_allowed: !state.internet_blocked, api_connection_allowed: true } });
      if (url.startsWith('/api/simulator')) {
        if (req.method() !== 'GET') {
          expect(req.headers()['if-match']).toBe(String(state.revision));
          if (url.endsWith('/connectivity')) state.internet_blocked = req.postDataJSON().internet_blocked;
          if (url.endsWith('/scenario')) state.enabled = true;
          state.revision++;
        }
        return route.fulfill({ json: state });
      }
      if (url === '/api/incidents' && req.method() === 'GET') return route.fulfill({ json: chat ? [chat] : [] });
      if (url === '/api/incidents' && req.method() === 'POST') {
        chat = { id: 'restricted', mode: 'general', title: 'Remote breakdown check', vehicle: {}, messages: [], safety: null };
        return route.fulfill({ status: 201, json: chat });
      }
      if (url.endsWith('/messages')) {
        expect(state.internet_blocked).toBe(true);
        expect(req.postData()).toContain('name="sensor_check"\r\n\r\ntrue');
        chat.messages.push({ id: 'gemma-reply', role: 'assistant', provider: 'gemma', model: 'gemma-4-26b-a4b-it', text: 'The rear-left tire reads 1.8 bar. I cannot check web references in this mode; compare the pressure with the vehicle label while safely parked.', state: 'complete', attachments: [], citations: [], search_suggestions: [], diagnostic_inference: [], follow_up_question: null, activity: [{ id: 'gemma', tool: 'gemma', initiator: 'backend', status: 'complete', summary: 'Gemma 4 26B analysis complete', timestamp: now }] });
        return route.fulfill({ status: 202, json: chat });
      }
      return route.fulfill({ status: 404, json: { detail: 'Unexpected route' } });
    });

    await page.goto('/simulator');
    await expect(page).toHaveTitle(/^AutoSage/);
    await expect(page.getByRole('heading', { name: 'Vehicle simulator' })).toBeVisible();
    const checkbox = page.getByRole('checkbox', { name: 'Block internet access (remote breakdown)' });
    await expect(checkbox).toBeEnabled();
    await checkbox.click();
    await expect(checkbox).toBeChecked();
    await expect(page.getByRole('region', { name: 'Remote breakdown simulation' })).toContainText('Gemma 4 26B only');
    await expect(page.getByRole('region', { name: 'Remote breakdown simulation' })).toContainText('The Gemini API connection stays allowed');
    await page.getByRole('button', { name: 'Tire pressure loss', exact: true }).click();
    await expect(checkbox).toBeChecked();
    await page.getByRole('button', { name: 'Reset all', exact: true }).click();
    await expect(checkbox).toBeChecked();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator('vite-error-overlay')).toHaveCount(0);
    if (process.env.QA_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.QA_SCREENSHOT_DIR, `remote-breakdown-${width}.png`), animations: 'disabled' });

    const customer = await context.newPage();
    await customer.setViewportSize({ width, height: 900 });
    await customer.goto('/');
    await expect(customer.locator('.connectivity-notice')).toContainText('Remote breakdown mode · Gemma 4 26B');
    await customer.getByRole('button', { name: 'Check what’s wrong with my car', exact: true }).click();
    await expect(customer.getByText(/The rear-left tire reads 1.8 bar/)).toBeVisible();
    await expect(customer.locator('.model-attribution')).toHaveText('Gemma 4 26B · Web access blocked');
    await customer.locator('.investigation-dropdown > summary').click();
    await expect(customer.locator('.investigation-activity')).toContainText('Analyzing with Gemma 4 26B');
    if (process.env.QA_SCREENSHOT_DIR) await customer.screenshot({ path: path.join(process.env.QA_SCREENSHOT_DIR, `remote-breakdown-chat-${width}.png`), animations: 'disabled' });
    await checkbox.click();
    await expect(page.getByRole('region', { name: 'Remote breakdown simulation' })).toContainText('Standard mode');
    await expect(customer.locator('.connectivity-notice')).toHaveCount(0);
    await expect(customer.locator('.model-attribution')).toBeVisible(); // Historical response keeps its provider.
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('stale connectivity changes require explicit reload before another write', async ({ page }) => {
  let revision = 2;
  let blocked = false;
  await page.route('**/api/**', async route => {
    const req = route.request();
    const url = new URL(req.url()).pathname;
    if (url === '/api/health') return route.fulfill({ json: { configured: true } });
    if (url === '/api/incidents') return route.fulfill({ json: [] });
    if (req.method() === 'PATCH') {
      if (req.headers()['if-match'] !== String(revision)) return route.fulfill({ status: 409, json: { detail: 'Simulator changed in another tab. Reload readings before applying this edit.' } });
      blocked = req.postDataJSON().internet_blocked;
      revision++;
    }
    return route.fulfill({ json: { enabled: false, internet_blocked: blocked, revision, snapshot_time: new Date().toISOString(), channels: {}, groups: {} } });
  });
  await page.goto('/simulator');
  const checkbox = page.getByRole('checkbox', { name: 'Block internet access (remote breakdown)' });
  await expect(checkbox).toBeEnabled();
  revision++;
  blocked = true;
  await checkbox.click();
  await expect(page.getByRole('alert')).toContainText('another tab');
  await expect(checkbox).toBeDisabled();
  await page.getByRole('button', { name: 'Reload readings' }).click();
  await expect(checkbox).toBeChecked();
  await expect(checkbox).toBeEnabled();
  await checkbox.click();
  await expect(checkbox).not.toBeChecked();
});
