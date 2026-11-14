import { test, expect } from '@playwright/test';

test('chat, gallery upload, playback, safety, and new conversation', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', {name:'Tire pressure warning', exact:true})).toBeVisible();
  await expect(page).toHaveTitle(/AutoSage/);
  await page.getByRole('button',{name:'Start new chat',exact:true}).click();
  await page.getByRole('button', {name:'Attach',exact:true}).click();
  await expect(page.getByRole('button',{name:'Upload video',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('input[type=file]').setInputFiles({name:'dashboard.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7i8AAAAASUVORK5CYII=','base64')});
  await page.getByRole('textbox',{name:'Message'}).fill('My tire warning is yellow');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.sent-media img')).toHaveCount(1);
  await page.getByRole('textbox',{name:'Message'}).fill('My brake pedal feels soft');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.safety')).toContainText('Do not continue driving');
  await page.getByRole('button',{name:'Start new chat',exact:true}).click();
  await expect(page.getByRole('heading',{name:'What’s happening with your car?'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('real browser audio and camera recording review, cancel, and send', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button',{name:'Start new chat',exact:true}).click();
  for (const kind of ['Voice','Camera']) {
    await page.getByRole('button',{name:kind,exact:true}).click();
    await page.getByRole('button',{name:'Start recording'}).click();
    await expect(page.getByRole('button',{name:'Stop recording'})).toBeVisible();
    await page.waitForTimeout(1200);
    await page.getByRole('button',{name:'Stop recording'}).click();
    await expect(page.getByText('Recording complete · devices are off')).toBeVisible();
    await page.getByRole('button',{name:kind === 'Voice' ? 'Use audio' : 'Use clip',exact:true}).click();
  }
  await expect(page.locator('.draft audio')).toHaveCount(1);
  await expect(page.locator('.draft video')).toHaveCount(1);
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.sent-media audio')).toHaveCount(1);
  await expect(page.locator('.sent-media video')).toHaveCount(1);
  const playback = await page.locator('.sent-media video').evaluate(async (v: HTMLVideoElement) => { await v.play(); return !v.paused; });
  expect(playback).toBe(true);
  await page.getByRole('button',{name:'Voice',exact:true}).click();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('mobile layout, permission failure and backend failure preserve draft', async ({ page, context }) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Open navigation'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.clearPermissions();
  await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = async () => {throw new DOMException('Permission denied','NotAllowedError');}; });
  await page.reload();
  await page.getByRole('button',{name:'Camera',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Permission denied');
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.route('**/api/incidents/*/messages', route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Backend unavailable'})}));
  await page.getByRole('textbox',{name:'Message'}).fill('Keep this draft');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.app-error')).toContainText('Your draft is preserved');
  await expect(page.getByRole('textbox',{name:'Message'})).toHaveValue('Keep this draft');
});
