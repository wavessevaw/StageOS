import {test,expect} from '@playwright/test';
test('Leaving the production editor returns to the repertoire grid',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'Добавить спектакль',exact:true}).first().click();
 await expect(page.getByRole('button',{name:'Сохранить постановку',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Календарь',exact:true}).first().click();
 await page.getByRole('button',{name:'Постановки',exact:true}).first().click();
 await expect(page.locator('.production-card').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'Сохранить постановку',exact:true})).toHaveCount(0);
});
