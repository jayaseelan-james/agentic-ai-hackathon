import {test,expect} from '@playwright/test';

test('remote breakdown toggle reaches the real backend and survives reload',async({page})=>{
 const originalResponse=await page.request.get('/api/simulator');expect(originalResponse.ok()).toBe(true);
 const original=await originalResponse.json();
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 try{
  await page.goto('/simulator');await expect(page.getByRole('heading',{name:'Vehicle simulator'})).toBeVisible();
  const checkbox=page.getByRole('checkbox',{name:'Block internet access (remote breakdown)'});
  await expect(checkbox).toBeEnabled();
  await checkbox.click();await expect(checkbox).toBeChecked({checked:!original.internet_blocked});
  await expect(page.getByRole('alert')).toHaveCount(0);
  const health=await (await page.request.get('/api/health')).json();
  expect(health.internet_blocked).toBe(!original.internet_blocked);
  expect(health.web_search_allowed).toBe(!!original.internet_blocked);
  if(!original.internet_blocked)expect(health.model).toBe('gemma-4-26b-a4b-it');
  await page.reload();await expect(checkbox).toBeChecked({checked:!original.internet_blocked});
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:`${process.env.QA_SCREENSHOT_DIR}/simulator-live-fixed.png`,animations:'disabled'});
  expect(errors).toEqual([]);
 }finally{
  const current=await (await page.request.get('/api/simulator')).json();
  if(current.internet_blocked!==original.internet_blocked){
   const restored=await page.request.patch('/api/simulator/connectivity',{headers:{'If-Match':String(current.revision)},data:{internet_blocked:!!original.internet_blocked}});
   expect(restored.ok()).toBe(true);
  }
 }
});

test('shared simulator: all channels, scenarios, histories, stale drafts and mobile',async({page,context})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/simulator');await expect(page.locator('.reading-row')).toHaveCount(17);
 await page.getByRole('button',{name:'Tire pressure loss',exact:true}).click();
 await expect(page.getByLabel('Rear-left tire', {exact:true})).toHaveValue('1.8');
 await expect(page.getByRole('img',{name:'Rear-left tire history: 2.3 to 1.8 bar'})).toBeVisible();
 const row=page.locator('.reading-row').filter({has:page.getByLabel('Rear-left tire',{exact:true})});
 await page.getByLabel('Rear-left tire',{exact:true}).fill('1.7');
 const other=await context.newPage();await other.goto('/simulator');await other.getByRole('button',{name:'Battery voltage drop',exact:true}).click();
 await expect(other.getByLabel('Battery voltage',{exact:true})).toHaveValue('10.8');
 await row.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('alert')).toContainText('another tab');
 await expect(page.getByLabel('Rear-left tire',{exact:true})).toHaveValue('1.7');
 await page.getByRole('button',{name:'Reload readings',exact:true}).click();await expect(page.getByRole('alert')).toHaveCount(0);
 await page.getByRole('button',{name:'Tire pressure loss',exact:true}).click();
 await page.getByLabel('Starting value',{exact:true}).fill('2.4');await page.getByLabel('Ending value',{exact:true}).fill('1.6');await page.getByRole('button',{name:'Apply custom trend'}).click();
 await expect(page.getByRole('img',{name:/Rear-left tire history: 2.4 to 1.6/})).toBeVisible();
 await row.getByRole('button',{name:'Unavailable',exact:true}).click();await expect(row.locator('.reading-unit')).toContainText('Unavailable');
 await row.getByRole('button',{name:'Restore',exact:true}).click();await expect(page.getByLabel('Rear-left tire',{exact:true})).toHaveValue('2.3');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByText('Investigation inspector',{exact:true}).click();await expect(page.getByLabel('Inspect chat')).toBeVisible();
 expect(errors).toEqual([]);
});
