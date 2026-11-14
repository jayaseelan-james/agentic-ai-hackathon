import {test,expect} from '@playwright/test';
for(const width of [1280,390])test(`live activity and domain probability charts at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const event=(tool:string,result:any={},status='complete')=>({id:crypto.randomUUID(),tool,result,status,initiator:'model',timestamp:new Date().toISOString(),summary:tool==='google_search'?'Reference search underway':'Vehicle evidence updated'});
 const answer:any={id:'a',role:'assistant',text:'',attachments:[],state:'processing',activity:[event('google_search',{},'running')],citations:[],search_suggestions:[],diagnostic_inference:[],report:null};
 const chat={id:'test',title:'Vehicle investigation',vehicle:{make:'',model:'',year:null},safety:null,messages:[answer]};
 await page.route('**/api/health',r=>r.fulfill({json:{configured:true}}));await page.route('**/api/incidents',r=>r.fulfill({json:[chat]}));await page.route('**/api/incidents/test',r=>r.fulfill({json:chat}));
 await page.goto('/');await expect(page.locator('.activity')).toContainText('Searching the web');await expect(page.locator('.event-running')).toContainText('In progress');
 answer.activity[0].status='complete';answer.activity.push(event('read_vehicle_sensors',{readings:{tpms_rear_left_bar:{value:1.8,unit:'bar'},battery_voltage_v:{value:12.6,unit:'V'}},unavailable:['brake_pressure_bar']}));answer.activity.push(event('read_sensor_history',{history:{tpms_rear_left_bar:{unit:'bar',lookback_minutes:1440,samples:[{value:2.3},{value:null},{value:1.8}]}}}));
 answer.diagnostic_inference=['tire','brake','cooling','starting_charging','engine_running'].map(domain=>({domain,status:domain==='cooling'?'insufficient_evidence':'inconclusive',ranked_hypotheses:domain==='cooling'?[]:[{fault_id:'category_a',posterior:.7},{fault_id:'other',posterior:.3}],conflicts:[],reason:'More observations are needed.'}));
 await expect(page.getByRole('region',{name:'Bayesian probabilities'})).toBeVisible();await expect(page.locator('.probability-domain')).toHaveCount(5);await expect(page.locator('.probability-chart')).toHaveCount(4);await expect(page.locator('.probability-fill').first()).toHaveAttribute('style','width: 70%;');
 await expect(page.getByRole('region',{name:'Tires probabilities'})).toContainText('1.8 bar');await expect(page.getByRole('region',{name:'Tires probabilities'})).toContainText('2.3 → 1.8 bar');await expect(page.getByRole('region',{name:'Brakes probabilities'})).toContainText('Unavailable');await expect(page.getByRole('region',{name:'Cooling probabilities'})).toContainText('Probabilities unavailable');
 answer.state='complete';answer.text='The pressure has decreased. A physical inspection is needed to identify the cause.';answer.activity.push(event('evaluate_safety'));
 await expect(page.locator('.processing')).toHaveCount(0);await expect(page.locator('.activity')).toContainText('Checking safety');await expect(page.locator('.probability-note')).toContainText('not validated diagnostic confidence');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('.bayesian-results').scrollIntoViewIfNeeded();if(process.env.QA_DIR)await page.screenshot({path:`${process.env.QA_DIR}/probabilities-${width}.png`});expect(errors).toEqual([]);
});
