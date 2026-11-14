import {test,expect} from '@playwright/test';
test('customer chat keeps operator diagnostics off the page',async({page})=>{
 await page.goto('/');await expect(page.locator('.demo-sensors,.diagnostic-details,.operator-inspector,.activity')).toHaveCount(0);
 await expect(page.locator('.notice')).toHaveCount(0);await expect(page.locator('.chat-header')).not.toContainText('Vehicle details not provided');
});
