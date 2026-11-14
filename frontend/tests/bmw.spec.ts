import { test, expect } from '@playwright/test';

test('BMW 330i G20 tab shares chat UI, isolates BMW chats, and uses shared simulator readings', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  const chats: any[] = [
    { id: 'gen-1', mode: 'general', title: 'Existing general chat', vehicle: { make: 'Toyota', model: 'Corolla', year: 2020 }, safety: null, messages: [] },
  ];
  let simRevision = 3;

  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const respond = (data: unknown, status = 200) => route.fulfill({ status, json: data });

    if (path === '/api/health') return respond({ configured: true, verified: true, provider: 'gemini', model: 'test-model' });
    if (path === '/api/simulator' && req.method() === 'GET') {
      return respond({
        enabled: true,
        source: 'simulated',
        fixture_id: 'demo-sensors-v1',
        revision: simRevision,
        snapshot_time: new Date().toISOString(),
        groups: { Tires: ['tpms_rear_left_bar'] },
        scenarios: [{ id: 'tire_pressure_loss', label: 'Tire pressure loss', description: 'Rear-left falls from 2.3 to 1.8 bar.' }],
        channels: {
          tpms_rear_left_bar: {
            name: 'tpms_rear_left_bar',
            label: 'Rear-left tire',
            unit: 'bar',
            value: 1.8,
            available: true,
            scenario: 'tire_pressure_loss',
            lookback_minutes: 1440,
            samples: [{ timestamp: new Date(Date.now() - 3600_000).toISOString(), value: 2.3 }, { timestamp: new Date().toISOString(), value: 1.8 }],
            limits: { min: 0, max: 10 },
            step: 0.01,
          },
        },
      });
    }
    if (path === '/api/incidents' && req.method() === 'GET') return respond(chats);
    if (path === '/api/incidents' && req.method() === 'POST') {
      const body = req.postDataJSON() || {};
      const isBmw = body.mode === 'bmw_g20';
      const created = {
        id: 'bmw-1',
        mode: isBmw ? 'bmw_g20' : 'general',
        title: 'New chat',
        vehicle: isBmw ? { make: 'BMW', model: '330i (G20)', year: null } : { make: '', model: '', year: null },
        safety: null,
        messages: [],
      };
      chats.unshift(created);
      return respond(created, 201);
    }
    if (path.endsWith('/messages') && req.method() === 'POST') {
      const updated = {
        id: 'bmw-1',
        mode: 'bmw_g20',
        title: 'My yellow TPMS warning is showing on iDrive.',
        vehicle: { make: 'BMW', model: '330i (G20)', year: 2021 },
        safety: null,
        messages: [
          { id: 'u1', role: 'user', text: 'My yellow TPMS warning is showing on iDrive.', state: 'complete', attachments: [], activity: [], citations: [], search_suggestions: [], diagnostic_inference: [], follow_up_question: null, report: null },
          {
            id: 'a1',
            role: 'assistant',
            text: 'Rear-left tire pressure is at 1.8 bar in the vehicle readings. Compare against your iDrive target and door-jamb placard while parked.',
            state: 'complete',
            error: null,
            provider: 'gemini',
            model: 'test-model',
            attachments: [],
            activity: [
              { id: 'ev1', tool: 'read_vehicle_sensors', initiator: 'model', status: 'complete', summary: 'Simulated current sensor readings retrieved', timestamp: new Date().toISOString() },
              { id: 'ev2', tool: 'search_bmw_knowledge', initiator: 'model', status: 'complete', summary: 'BMW 330i G20 knowledge cards retrieved', timestamp: new Date().toISOString() },
            ],
            citations: [{ url: 'https://www.bmw3g20.com/tire_pressure_monitor_tpm-3134.html', title: 'G20 TPMS system', start_index: null, end_index: null }],
            search_suggestions: [],
            diagnostic_inference: [{ domain: 'tire', status: 'ok', context: 'demo', evidence_revision: 1, model_version: 'v2', parameter_source: 'synthetic_training', calibration: 'uncalibrated', demo_only: true, ranked_hypotheses: [{ fault_id: 'tire_pressure_loss', posterior: 0.88 }, { fault_id: 'tpms_sensor_issue', posterior: 0.08 }, { fault_id: 'other_or_unmodeled', posterior: 0.04 }], evidence_used: [], evidence_ignored: [], conflicts: [], reason: 'Leading category', disclaimer: 'Synthetic' }],
            follow_up_question: { id: 'parked', text: 'Was the vehicle parked when these readings were recorded?', domain: 'tire', symptom: null, kind: 'conditions', information_gain: 0.2 },
            simulator_snapshot: { enabled: true, revision: simRevision, fixture_id: 'demo-sensors-v1', snapshot_time: new Date().toISOString() },
            report: null,
          },
        ],
      };
      chats[0] = updated;
      return respond(updated, 202);
    }
    return respond({ detail: 'Not mocked' }, 404);
  });

  await page.goto('/simulator');
  await expect(page.getByRole('link', { name: /BMW 330i G20/i })).toHaveAttribute('href', '/bmw');
  await expect(page.getByLabel('Rear-left tire', { exact: true })).toHaveValue('1.8');

  await page.goto('/');
  await expect(page.getByRole('tab', { name: 'General' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tab', { name: 'BMW 330i G20' })).toHaveAttribute('aria-selected', 'false');
  await expect(page.locator('.sidebar nav')).toContainText('Existing general chat');

  await page.getByRole('tab', { name: 'BMW 330i G20' }).click();
  await expect(page).toHaveURL(/\/bmw$/);
  await expect(page.getByRole('tab', { name: 'BMW 330i G20' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('.sidebar nav')).not.toContainText('Existing general chat');
  await expect(page.locator('.vehicle')).toContainText('BMW 330i (G20)');
  await expect(page.getByRole('heading', { name: 'What’s happening with your BMW 330i (G20)?' })).toBeVisible();

  await page.getByRole('button', { name: 'My yellow TPMS warning is showing on iDrive.' }).click();
  await expect(page.getByText('Rear-left tire pressure is at 1.8 bar')).toBeVisible();
  await expect(page.locator('.sources')).toContainText('G20 TPMS system');
  await page.locator('.investigation-dropdown > summary').click();
  await expect(page.locator('.investigation-activity')).toContainText('Checking BMW 330i G20 knowledge base');

  await page.getByRole('tab', { name: 'General' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('.sidebar nav')).toContainText('Existing general chat');
  await expect(page.locator('.sidebar nav')).not.toContainText('My yellow TPMS warning is showing on iDrive.');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/bmw');
  await expect(page.getByRole('tab', { name: 'BMW 330i G20' })).toHaveAttribute('aria-selected', 'true');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
