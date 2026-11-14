import {test,expect} from '@playwright/test';
test('customer chat keeps operator diagnostics off the page',async({page})=>{
 await page.goto('/');await expect(page.locator('.demo-sensors,.diagnostic-details,.operator-inspector,.activity')).toHaveCount(0);
 await expect(page.getByText('No vehicle connection.',{exact:false}).first()).toBeVisible();
});
