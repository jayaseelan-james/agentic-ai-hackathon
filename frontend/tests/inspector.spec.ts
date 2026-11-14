import {test,expect} from '@playwright/test';
test('operator inspector shows evidence, frozen snapshot and executed tools',async({page})=>{
 const message={id:'a',role:'assistant',timestamp:new Date().toISOString(),state:'complete',provider:'gemini',model:'test-model',simulator_snapshot:{revision:7,enabled:true},media_analysis:[{kind:'image',status:'analyzed',attachment_id:'picture'}],diagnostic_inference:[],activity:[{id:'e',tool:'record_observations',initiator:'model',status:'complete',summary:'Source-linked observations registered',arguments:{observations:[]},result:{accepted:[]}}]};
 await page.route('**/api/incidents',r=>r.fulfill({json:[{id:'test',title:'Evidence check'}]}));
 await page.route('**/api/incidents/test/inspection',r=>r.fulfill({json:{incident:{messages:[message]},evidence:[{id:'ev',symptom:'yellow_tpms_warning',value:true,source:'media_observed',attachment_id:'picture',context:'demo',superseded:false}],report:{uncertainties:['Unconfirmed']}}}));
 await page.goto('/simulator');await page.getByText('Investigation inspector',{exact:true}).click();await page.getByLabel('Inspect chat').selectOption('test');
 await expect(page.getByRole('region',{name:'Accepted evidence'})).toContainText('media observed');await expect(page.getByText('Simulator snapshot: revision 7',{exact:false})).toBeVisible();await page.getByText('Tool activity · 1 events',{exact:true}).click();await expect(page.locator('.inspection-event')).toContainText('record_observations');await expect(page.getByText('image · analyzed · picture',{exact:true})).toBeVisible();
});
