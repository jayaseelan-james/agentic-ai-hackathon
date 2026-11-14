import { test, expect, type Page } from '@playwright/test';

// Explicit test-only HTTP fixtures. Production has no mock provider or fallback.
async function fixture(page: Page) {
  const chats: any[] = [];
  const media = new Map<string, {body: Buffer; mime: string}>();
  let polls = 0;
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const respond = (data: unknown, status = 200) => route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
    if (path === '/api/health') return respond({configured:true,verified:true,provider:'gemini',model:'test-model'});
    if (path.includes('/sensors')) return respond({detail:'Sensor simulation is outside these Gemini UI fixtures.'},404);
    if (path.startsWith('/api/attachments/')) { const data = media.get(path)!; return route.fulfill({status:200,contentType:data.mime,body:data.body}); }
    if (path === '/api/incidents' && req.method() === 'GET') return respond(chats);
    if (path === '/api/incidents' && req.method() === 'POST') {const chat={id:crypto.randomUUID(),title:'New chat',vehicle:{make:'',model:'',year:null},messages:[],safety:null}; chats.push(chat); return respond(chat,201);}
    const chat=chats.find(c => path.includes(c.id));
    if (!chat) return respond({detail:'Not found'},404);
    if (path.endsWith('/vehicle')) {chat.vehicle=req.postDataJSON();return respond(chat);}
    if (path.endsWith('/retry')) {chat.messages.at(-1).state='processing';chat.messages.at(-1).error=null;polls=0;return respond(chat,202);}
    if (path.endsWith('/messages') && req.method() === 'POST') {
      const boundary=req.headers()['content-type'].split('boundary=')[1];
      const parts=req.postDataBuffer()!.toString('latin1').split('--'+boundary);
      let text='';const attachments: any[]=[];
      for(const part of parts) {
        const split=part.indexOf('\r\n\r\n');if(split<0)continue;
        const header=part.slice(0,split),body=part.slice(split+4).replace(/\r\n$/,'');
        if(header.includes('name="text"')) text=Buffer.from(body,'latin1').toString('utf8');
        const filename=header.match(/filename="([^"]+)"/)?.[1];
        if(filename){const mime=header.match(/Content-Type: ([^\r\n]+)/i)![1];const url='/api/attachments/'+crypto.randomUUID();media.set(url,{body:Buffer.from(body,'latin1'),mime});attachments.push({id:url,url,filename,mime_type:mime,kind:mime.split('/')[0],size:body.length});}
      }
      const user={id:crypto.randomUUID(),role:'user',text,attachments,state:'complete',activity:[],citations:[],search_suggestions:[]};
      const answer={id:crypto.randomUUID(),role:'assistant',text:'',attachments:[],state:'processing',error:null,provider:'gemini',model:'test-model',activity:[],citations:[],search_suggestions:[],report:null};
      if(text.includes('soft brake')){chat.safety='If driving, stop safely. Do not continue driving. Seek professional assistance.';answer.text=chat.safety;answer.state='complete';answer.provider='safety_rules';}
      chat.messages.push(user,answer);chat.title=text.slice(0,45)||'Media conversation';polls=0;return respond(chat,202);
    }
    const answer=chat.messages.at(-1);
    if(answer?.state==='processing' && ++polls >= 2) {
      answer.state='complete';answer.text='A tire warning needs investigation. Check the vehicle label while safely parked.';
      answer.citations=[{url:'https://example.com/manual',title:'Official source',start_index:0,end_index:35}];
      answer.activity=[{id:'event',tool:'google_search',initiator:'model',status:'complete',summary:'Manufacturer guidance retrieved',timestamp:new Date().toISOString()}];
      answer.search_suggestions=['<p>Google Search suggestions</p>'];
    }
    return respond(chat);
  });
}

test.beforeEach(async ({page}) => {await fixture(page);});

async function openChat(page: Page) {
  await page.goto('/');
  await page.getByRole('button',{name:'Start a conversation',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Message'})).toBeVisible();
}

test('vehicle details, processing, citations, tool activity, safety and new chat',async ({page})=>{
  const errors: string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&m.text().includes('same key'))errors.push(m.text());});
  await openChat(page);await expect(page).toHaveTitle(/AutoSage/);
  await expect(page.getByText('Edit vehicle details',{exact:true})).toHaveCount(0);
  await page.getByRole('textbox',{name:'Message'}).fill('My tire warning is yellow');await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.processing')).toBeVisible();
  await expect(page.locator('.sources')).toContainText('Official source');
  await expect(page.locator('.sources')).not.toBeVisible();
  await expect(page.locator('.search-suggestions')).not.toBeVisible();
  await page.locator('.investigation-dropdown > summary').click();
  await expect(page.locator('.sources')).toBeVisible();
  await expect(page.locator('.search-suggestions')).toBeVisible();
  await expect(page.locator('.activity')).toContainText('Searching the web');
  await expect(page.locator('.diagnostic-details, .demo-sensors')).toHaveCount(0);
  await expect(page.locator('.search-suggestions')).toHaveCount(1);
  await page.getByRole('textbox',{name:'Message'}).fill('My brake pedal feels soft brake');await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.safety')).toContainText('Do not continue driving');
  await page.getByRole('button',{name:'Start new chat'}).click();await expect(page.getByRole('heading',{name:'What’s happening with your car?'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('image upload and real browser audio/video recording, review and playback',async ({page})=>{
  await openChat(page);
  await page.locator('input[type=file]').setInputFiles({name:'dashboard.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7i8AAAAASUVORK5CYII=','base64')});
  for(const kind of ['Voice','Camera']) {
    await page.getByRole('button',{name:kind,exact:true}).click();await page.getByRole('button',{name:'Start recording'}).click();await page.waitForTimeout(1100);await page.getByRole('button',{name:'Stop recording'}).click();
    await expect(page.getByText('Recording complete · devices are off')).toBeVisible();await page.getByRole('button',{name:kind==='Voice'?'Use audio':'Use clip',exact:true}).click();
  }
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.sent-media img')).toHaveCount(1);await expect(page.locator('.sent-media audio')).toHaveCount(1);await expect(page.locator('.sent-media video')).toHaveCount(1);
  expect(await page.locator('.sent-media video').evaluate(async(v:HTMLVideoElement)=>{await v.play();return !v.paused;})).toBe(true);
  await expect(page.locator('.processing')).not.toBeVisible();
});

test('mobile permissions and rejected submission preserve draft',async ({page})=>{
  await page.setViewportSize({width:390,height:844});await openChat(page);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Permission denied','NotAllowedError');};});
  await page.getByRole('button',{name:'Camera',exact:true}).click();await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Permission denied');await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.route('**/api/incidents/*/messages',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Backend unavailable'})}));
  await page.getByRole('textbox',{name:'Message'}).fill('Keep this draft');await page.getByRole('button',{name:'Send message'}).click();await expect(page.locator('.app-error')).toContainText('Your draft is preserved');await expect(page.getByRole('textbox',{name:'Message'})).toHaveValue('Keep this draft');
});

test('failed generation retries the saved message',async ({page})=>{
  await openChat(page);
  let saved:any;let failed=true;
  // This fixture exercises rendering/retry without incurring paid provider calls.
  await page.route('**/api/incidents/*/messages',async route=>{
    const id=new URL(route.request().url()).pathname.split('/')[3];
    saved={id,title:'Retry test',vehicle:{make:'',model:'',year:null},safety:null,messages:[{id:'u',role:'user',text:'Retry test',state:'complete',attachments:[],activity:[],citations:[],search_suggestions:[]},{id:'a',role:'assistant',text:'',state:'failed',error:'Gemini quota reached',attachments:[],activity:[],citations:[],search_suggestions:[],provider:'gemini',model:'test-model'}]};
    await route.fulfill({status:202,json:saved});
  });
  await page.route('**/api/incidents/*/messages/a/retry',async route=>{failed=false;saved.messages[1].state='complete';saved.messages[1].error=null;saved.messages[1].text='Investigation recovered.';await route.fulfill({status:202,json:saved});});
  await page.getByRole('textbox',{name:'Message'}).fill('Retry test');await page.getByRole('button',{name:'Send message'}).click();await expect(page.getByText(/assistant is temporarily unavailable/i)).toBeVisible();await page.getByRole('button',{name:'Retry investigation'}).click();await expect(page.getByText('Investigation recovered.')).toBeVisible();expect(failed).toBe(false);
});
