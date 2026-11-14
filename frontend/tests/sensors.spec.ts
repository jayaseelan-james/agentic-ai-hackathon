import { test, expect, type Page } from '@playwright/test';

// Real local simulator API. Model requests in the failure scenario below are explicit HTTP fixtures.
async function openDemo(page: Page) {
  const response = await page.request.post('/api/incidents', {data: {}});
  expect(response.status()).toBe(201);
  const chat = await response.json();
  await page.goto('/');
  await page.locator('.demo-sensors > summary').click();
  await expect(page.getByLabel('Enable demo sensors')).toBeVisible();
  await page.getByLabel('Enable demo sensors').check();
  await expect(page.getByRole('button', {name: 'Apply preset', exact: true})).toBeEnabled();
  return chat;
}

test('stable pressure-loss demo, refresh, single-sensor edits, custom trend and reset', async ({page}) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {if (['warning', 'error'].includes(message.type())) errors.push(message.text());});
  const chat = await openDemo(page);
  await expect(page).toHaveTitle(/AutoSage/);
  await expect(page.getByRole('button', {name: 'Rear-left tire 2.3 bar'})).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', {name: 'Apply preset', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Rear-left tire 1.8 bar'})).toBeVisible();
  await expect(page.getByRole('img', {name: 'Rear-left tire history: 2.3 to 1.8 bar'})).toBeVisible();
  await expect(page.locator('.message')).toHaveCount(0);
  const first = await (await page.request.get(`/api/incidents/${chat.id}/sensors`)).json();
  await page.locator('.sensor-history').scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', {name: 'Send message'})).toBeInViewport();
  if (process.env.SENSOR_QA_DIR) await page.screenshot({path: `${process.env.SENSOR_QA_DIR}/sensors-desktop.png`});
  await page.reload();
  await page.locator('.demo-sensors > summary').click();
  await expect(page.getByLabel('Enable demo sensors')).toBeChecked();
  await expect(page.getByRole('button', {name: 'Rear-left tire 1.8 bar'})).toBeVisible();
  const second = await (await page.request.get(`/api/incidents/${chat.id}/sensors`)).json();
  expect(second.channels).toEqual(first.channels);
  expect(second.snapshot_time).toBe(first.snapshot_time);
  await page.getByText('Timestamped samples', {exact: true}).click();
  await expect(page.locator('.sensor-history tbody tr')).toHaveCount(61);
  await page.getByRole('button', {name: 'Front-left tire 2.3 bar'}).click();
  await page.getByLabel('Current value (bar)', {exact: true}).fill('2');
  await page.getByRole('button', {name: 'Set value', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Front-left tire 2 bar'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Rear-left tire 1.8 bar'})).toBeVisible();
  await page.getByRole('button', {name: 'Mark unavailable'}).click();
  await expect(page.getByRole('button', {name: 'Front-left tire Unavailable'})).toBeVisible();
  await page.getByRole('button', {name: 'Restore sensor'}).click();
  await expect(page.getByRole('button', {name: 'Front-left tire 2.3 bar'})).toBeVisible();
  await page.getByRole('button', {name: 'Rear-left tire 1.8 bar'}).click();
  await page.getByText('Custom trend', {exact: true}).click();
  await page.getByLabel('Starting value (bar)', {exact: true}).fill('2.4');
  await page.getByLabel('Ending value (bar)', {exact: true}).fill('1.6');
  await page.getByLabel('Duration (minutes)', {exact: true}).fill('180');
  await page.getByRole('button', {name: 'Apply custom trend'}).click();
  await expect(page.getByRole('img', {name: 'Rear-left tire history: 2.4 to 1.6 bar'})).toBeVisible();
  await expect(page.locator('.sensor-history-heading')).toContainText('180 minute window');
  await page.getByRole('button', {name: 'Reset all', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Rear-left tire 2.3 bar'})).toBeVisible();
  await expect(page.getByRole('img', {name: 'Rear-left tire history: 2.3 to 2.3 bar'})).toBeVisible();
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.querySelector('vite-error-overlay'))).toBeNull();
});

test('mobile coolant and RPM presets fit the screen and isolate new chats', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {if (['warning', 'error'].includes(message.type())) errors.push(message.text());});
  await openDemo(page);
  await page.getByRole('button', {name: 'Coolant temperature 22 °C'}).click();
  await page.getByRole('button', {name: 'Apply preset', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Coolant temperature 110 °C'})).toBeVisible();
  await expect(page.getByRole('img', {name: 'Coolant temperature history: 22 to 110 °C'})).toBeVisible();
  await page.locator('.sensor-history').scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', {name: 'Send message'})).toBeInViewport();
  if (process.env.SENSOR_QA_DIR) await page.screenshot({path: `${process.env.SENSOR_QA_DIR}/sensors-mobile.png`});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', {name: 'Engine RPM 0 RPM'}).click();
  await page.getByRole('button', {name: 'Apply preset', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Engine RPM 1800 RPM'})).toBeVisible();
  await expect(page.locator('.sensor-history-heading')).toContainText('2 minute window');
  await page.getByRole('button', {name: 'Open navigation'}).click();
  await page.getByRole('button', {name: 'Start new chat'}).click();
  await page.locator('.demo-sensors > summary').click();
  await expect(page.getByLabel('Enable demo sensors')).not.toBeChecked();
  await expect(page.getByRole('button', {name: 'Engine RPM 0 RPM'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('processing locks mutations and provider failure retains simulator values', async ({page}) => {
  const chat = await openDemo(page);
  await page.getByRole('button', {name: 'Apply preset', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Rear-left tire 1.8 bar'})).toBeVisible();
  const processing = {...chat, title: 'Investigate pressure', messages: [{id: 'answer', role: 'assistant', state: 'processing', text: '', attachments: [], activity: [], citations: [], search_suggestions: [], provider: 'gemini', model: 'test-model'}]};
  let failed = false;
  await page.route(`**/api/incidents/${chat.id}/messages`, route => route.fulfill({status: 202, json: processing}));
  await page.route(`**/api/incidents/${chat.id}`, route => route.fulfill({json: failed ? {...processing, messages: [{...processing.messages[0], state: 'failed', error: 'Gemini request failed. Please retry.'}]} : processing}));
  await page.getByRole('textbox', {name: 'Message', exact: true}).fill('Investigate this gradual tire pressure decline.');
  await page.getByRole('button', {name: 'Send message'}).click();
  await expect(page.getByLabel('Enable demo sensors')).toBeDisabled();
  await expect(page.getByRole('button', {name: 'Apply preset', exact: true})).toBeDisabled();
  await expect(page.getByRole('button', {name: 'Reset all', exact: true})).toBeDisabled();
  failed = true;
  await expect(page.getByText('Gemini request failed. Please retry.')).toBeVisible();
  await expect(page.getByLabel('Enable demo sensors')).toBeEnabled();
  await expect(page.getByRole('button', {name: 'Rear-left tire 1.8 bar'})).toBeVisible();
});
