import { test, expect, type Page } from '@playwright/test';

type Options = { transcriptDelay?: number; speechDelay?: number; failTranscription?: boolean; failSpeech?: boolean; history?: boolean; immediate?: boolean };

async function setup(page: Page, options: Options = {}) {
  const state = {speech: 0, transcriptions: 0, sends: 0, submitted: ''};
  await page.addInitScript(() => {
    const state = {plays: 0, pauses: 0, block: false};
    (window as any).__speech = state;
    HTMLMediaElement.prototype.play = function () { state.plays++; return state.block ? Promise.reject(new DOMException('Blocked', 'NotAllowedError')) : Promise.resolve(); };
    HTMLMediaElement.prototype.pause = function () { state.pauses++; };
  });
  const answer = (id: string) => ({id, role: 'assistant', text: 'The cause is unconfirmed. Is the warning steady?', state: 'complete', attachments: [], activity: [], citations: [], search_suggestions: [], error: null, provider: 'gemini', model: 'test'});
  const chats: any[] = options.history ? [{id: 'old', mode: 'general', title: 'Earlier conversation', vehicle: {}, safety: null, messages: [answer('old-answer')]}] : [];
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({status, json: body});
    if (path === '/api/health') return json({configured: true, provider: 'gemini', model: 'test'});
    if (path === '/api/speech/transcriptions') {
      state.transcriptions++;
      if (options.transcriptDelay) await new Promise(resolve => setTimeout(resolve, options.transcriptDelay));
      if (options.failTranscription && state.transcriptions === 1) return json({detail: 'Google speech is unavailable. Retry transcription.'}, 502);
      return json({text: 'My yellow tire warning is on.'});
    }
    if (path === '/api/attachments/speech') {
      const wav = Buffer.alloc(32044);
      wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
      wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
      wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28); wav.writeUInt16LE(2, 32);
      wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(32000, 40);
      return route.fulfill({contentType: 'audio/wav', body: wav});
    }
    if (path.endsWith('/speech')) {
      state.speech++;
      if (options.speechDelay) await new Promise(resolve => setTimeout(resolve, options.speechDelay));
      if (options.failSpeech && state.speech === 1) return json({detail: 'Google speech is unavailable. Retry speech.'}, 502);
      return json({text: 'The cause is unconfirmed. Is the warning steady?', audio_url: '/api/attachments/speech', mime_type: 'audio/wav'});
    }
    if (path === '/api/incidents' && req.method() === 'GET') return json(chats);
    if (path === '/api/incidents' && req.method() === 'POST') {
      const chat = {id: `chat-${chats.length}`, title: 'New chat', mode: req.postDataJSON()?.mode || 'general', vehicle: {}, safety: null, messages: []};
      chats.unshift(chat); return json(chat, 201);
    }
    const chat = chats.find(c => path.includes(c.id));
    if (!chat) return json({detail: 'Not found'}, 404);
    if (path.endsWith('/messages') && req.method() === 'POST') {
      state.sends++;
      state.submitted = req.postDataBuffer()!.toString('utf8');
      chat.title = 'Tire warning';
      chat.messages.push({...answer(`answer-${state.sends}`), state: options.immediate ? 'complete' : 'processing'});
      return json(chat, 202);
    }
    chat.messages.forEach((m: any) => { m.state = 'complete'; });
    return json(chat);
  });
  return state;
}

async function openChat(page: Page, path = '/') {
  await page.goto(path);
  await page.getByRole('button', {name: 'Start a conversation', exact: true}).click();
  await expect(page.getByRole('textbox', {name: 'Message'})).toBeVisible();
}

async function dictate(page: Page) {
  await page.getByRole('button', {name: 'Voice', exact: true}).click();
  await page.getByRole('button', {name: 'Start recording', exact: true}).click();
  await page.waitForTimeout(350);
  await page.getByRole('button', {name: 'Stop recording', exact: true}).click();
}

async function send(page: Page) {
  await page.getByRole('textbox', {name: 'Message'}).fill('Yellow tire warning');
  await page.getByRole('button', {name: 'Send message'}).click();
}

for (const [path, width] of [['/', 1280], ['/bmw', 390]] as const) {
  test(`dictation is editable and new answer speaks once at ${path}`, async ({page}) => {
    await page.setViewportSize({width, height: 900});
    const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
    const state = await setup(page, {transcriptDelay: 500});
    await openChat(page, path);
    await page.getByRole('textbox', {name: 'Message'}).fill('Existing draft');
    await dictate(page);
    await expect(page.getByText('Transcribing…', {exact: true})).toBeVisible();
    await page.getByRole('textbox', {name: 'Message'}).fill('Edited while waiting');
    await expect(page.getByRole('textbox', {name: 'Message'})).toHaveValue('Edited while waiting\nMy yellow tire warning is on.');
    expect(state.sends).toBe(0);
    await page.getByRole('button', {name: 'Send message'}).click();
    await expect(page.getByRole('button', {name: 'Stop speaking'})).toBeVisible();
    expect(state.submitted.replace(/\r\n/g, '\n')).toContain('Edited while waiting\nMy yellow tire warning is on.');
    await page.getByText('Spoken summary', {exact: true}).click();
    await expect(page.locator('.speech-controls details')).toContainText('The cause is unconfirmed.');
    await page.waitForTimeout(1200);
    expect(state.speech).toBe(1);
    expect(await page.evaluate(() => (window as any).__speech.plays)).toBe(1);
    expect(errors).toEqual([]);
    await expect(page.locator('vite-error-overlay')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: `C:/Users/prati/.codex/visualizations/2026/11/14/01a1daf2-6476-7f82-b4a0-3198e9eed442/speech-${width}.png`});
    await page.getByRole('button', {name: 'Voice', exact: true}).click();
    await expect(page.getByRole('button', {name: 'Stop speaking'})).toHaveCount(0);
    await page.getByRole('button', {name: 'Close recorder'}).click();
  });
}

test('transcription failure preserves draft and recording for retry', async ({page}) => {
  const state = await setup(page, {failTranscription: true});
  await openChat(page);
  await page.getByRole('textbox', {name: 'Message'}).fill('Original draft');
  await dictate(page);
  await expect(page.getByRole('button', {name: 'Retry transcription'})).toBeVisible();
  await expect(page.getByRole('textbox', {name: 'Message'})).toHaveValue('Original draft');
  await page.getByRole('button', {name: 'Retry transcription'}).click();
  await expect(page.getByRole('textbox', {name: 'Message'})).toHaveValue('Original draft\nMy yellow tire warning is on.');
  expect(state.sends).toBe(0); expect(state.transcriptions).toBe(2);
});

test('canceled transcription never appends its late result', async ({page}) => {
  await setup(page, {transcriptDelay: 800});
  await openChat(page);
  await page.getByRole('textbox', {name: 'Message'}).fill('Keep this');
  await dictate(page);
  await expect(page.getByText('Transcribing…', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Cancel dictation'}).click();
  await page.waitForTimeout(1000);
  await expect(page.getByRole('textbox', {name: 'Message'})).toHaveValue('Keep this');
});

test('leaving a chat discards its pending transcription', async ({page}) => {
  await setup(page, {transcriptDelay: 800});
  await openChat(page);
  await dictate(page);
  await expect(page.getByText('Transcribing…', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Start new chat'}).click();
  await page.waitForTimeout(1000);
  await expect(page.getByRole('textbox', {name: 'Message'})).toHaveValue('');
  await expect(page.getByText('Transcribing…', {exact: true})).toHaveCount(0);
});

test('a quick prompt creating a chat speaks its immediate answer', async ({page}) => {
  const state = await setup(page, {immediate: true});
  await page.goto('/');
  await page.getByRole('button', {name: 'Check what’s wrong with my car', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Stop speaking'})).toBeVisible();
  expect(state.speech).toBe(1);
});

test('navigation cancels pending speech and history never autoplays', async ({page}) => {
  const state = await setup(page, {speechDelay: 800, history: true});
  await page.goto('/');
  await expect(page.getByText('Earlier conversation').first()).toBeVisible();
  expect(state.speech).toBe(0);
  await send(page);
  await expect(page.getByText('Preparing speech…')).toBeVisible();
  await page.getByRole('button', {name: 'Start new chat'}).click();
  await page.waitForTimeout(1000);
  expect(await page.evaluate(() => (window as any).__speech.plays)).toBe(0);
  await page.getByRole('button', {name: 'Tire warning', exact: true}).click();
  await page.waitForTimeout(300);
  expect(state.speech).toBe(1);
});

test('mute persists and manual replay remains available', async ({page}) => {
  const state = await setup(page, {immediate: true});
  await openChat(page);
  await page.getByRole('button', {name: 'Mute spoken answers'}).click();
  await send(page);
  await expect(page.getByRole('button', {name: 'Play answer'})).toBeVisible();
  expect(state.speech).toBe(0);
  await page.reload();
  await expect(page.getByRole('button', {name: 'Enable spoken answers'})).toBeVisible();
  expect(state.speech).toBe(0);
  await page.getByRole('button', {name: 'Play answer'}).click();
  await expect(page.getByRole('button', {name: 'Stop speaking'})).toBeVisible();
  await page.getByRole('button', {name: 'Stop speaking'}).click();
  await expect(page.getByRole('button', {name: 'Play answer'})).toBeVisible();
});

test('autoplay rejection offers play button and can be retried', async ({page}) => {
  await setup(page, {immediate: true});
  await openChat(page);
  await page.evaluate(() => { (window as any).__speech.block = true; });
  await send(page);
  await expect(page.getByText('Playback needs a tap. Select Play answer.')).toBeVisible();
  await page.evaluate(() => { (window as any).__speech.block = false; });
  await page.getByRole('button', {name: 'Play answer'}).click();
  await expect(page.getByRole('button', {name: 'Stop speaking'})).toBeVisible();
});

test('speech failure leaves written answer available with retry', async ({page}) => {
  const state = await setup(page, {failSpeech: true});
  await openChat(page);
  await send(page);
  await expect(page.getByRole('button', {name: 'Retry speech'})).toBeVisible();
  await expect(page.locator('.answer-markdown')).toContainText('The cause is unconfirmed.');
  await page.getByRole('button', {name: 'Retry speech'}).click();
  await expect(page.getByRole('button', {name: 'Stop speaking'})).toBeVisible();
  expect(state.speech).toBe(2);
});
