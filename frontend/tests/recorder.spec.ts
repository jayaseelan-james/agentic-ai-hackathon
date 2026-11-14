import { test, expect } from '@playwright/test';

for (const viewport of [{width:1280,height:900},{width:390,height:844}]) {
  test(`camera clip plays in review before attachment at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    const errors: string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      const json=(body:unknown,status=200)=>route.fulfill({status,json:body});
      if(path==='/api/health')return json({configured:true,verified:false,model:'test-model',provider:'gemini'});
      if(path==='/api/incidents'&&route.request().method()==='GET')return json([]);
      if(path==='/api/incidents'&&route.request().method()==='POST')return json({id:'recording-test',title:'New chat',vehicle:{make:'',model:'',year:null},messages:[],safety:null},201);
      return json({detail:'Outside recorder test scope'},404);
    });
    await page.goto('/');
    await page.getByRole('button',{name:'Start a conversation',exact:true}).click();
    for(let attempt=0;attempt<2;attempt++) {
      await page.getByRole('button',{name:'Camera',exact:true}).click();
      const dialog=page.getByRole('dialog');
      await dialog.getByRole('button',{name:'Start recording'}).click();
      await page.waitForTimeout(1400);
      await dialog.getByRole('button',{name:'Stop recording'}).click();
      await expect(dialog.getByRole('heading',{name:'Review video'})).toBeVisible();
      const preview=dialog.locator('video');
      // A Blob URL cannot play while srcObject still selects the stopped stream.
      expect(await preview.evaluate((video:HTMLVideoElement)=>video.srcObject===null)).toBe(true);
      await expect.poll(()=>preview.evaluate((video:HTMLVideoElement)=>video.readyState)).toBeGreaterThanOrEqual(2);
      await preview.evaluate((video:HTMLVideoElement)=>video.play());
      await expect.poll(()=>preview.evaluate((video:HTMLVideoElement)=>video.currentTime)).toBeGreaterThan(.15);
      expect(await preview.evaluate((video:HTMLVideoElement)=>({muted:video.muted,paused:video.paused,controls:video.controls,autoplay:video.autoplay,error:video.error?.code??null}))).toEqual({muted:false,paused:false,controls:true,autoplay:false,error:null});
      await preview.evaluate((video:HTMLVideoElement)=>{video.pause();video.currentTime=0;});
      await preview.evaluate((video:HTMLVideoElement)=>video.play());
      await expect.poll(()=>preview.evaluate((video:HTMLVideoElement)=>video.currentTime)).toBeGreaterThan(.15);
      if(attempt===0)await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
      else await dialog.getByRole('button',{name:'Use clip',exact:true}).click();
      await expect(dialog).not.toBeVisible();
    }
    await expect(page.locator('.draft video')).toHaveCount(1);
    expect(errors).toEqual([]);
  });
}
