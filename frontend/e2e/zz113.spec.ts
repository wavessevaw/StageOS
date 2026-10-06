import {test,expect} from '@playwright/test';
test('General call fits the appointment screen and multiple responsibles fit the passport',async({page})=>{
 await page.request.post('/api/demo');await page.goto('/');
 await expect(page.getByRole('heading',{name:'Поднимем занавес.'})).toBeVisible();
 const arts=page.locator('.arts-people');await expect(arts).toBeVisible();
 await arts.getByRole('button',{name:'Добавить всех',exact:true}).click();
 await arts.locator('summary').click();
 expect(await arts.locator('input:checked').count()).toBeGreaterThan(20);
 const fit=await arts.evaluate(el=>el.scrollWidth<=el.clientWidth+1);expect(fit).toBeTruthy();
 await page.screenshot({path:'../docs/113-general-call.png',fullPage:true});
 await page.getByRole('button',{name:'Постановки',exact:true}).first().click();
 await page.locator('.production-card').first().click();
 await page.getByRole('button',{name:'Редактировать постановку',exact:true}).click();
 await page.getByRole('button',{name:'Люди',exact:true}).click();
 const sound=page.locator('.responsible-picker').filter({has:page.locator('legend',{hasText:'Звук'})});
 await expect(sound).toBeVisible();expect(await sound.getByRole('checkbox').count()).toBeGreaterThan(1);
 await sound.getByRole('checkbox').nth(1).check();
 expect(await sound.getByRole('checkbox',{checked:true}).count()).toBeGreaterThan(1);
 expect(await sound.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await sound.scrollIntoViewIfNeeded();
 await page.screenshot({path:'../docs/113-responsibles.png',fullPage:false});
});

test('Every production stage including the performance can be removed',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Проверить и назначить',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Предварительный план'});await expect(dialog).toBeVisible();
 await dialog.getByRole('button',{name:'Удалить этап Спектакль',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Восстановить: Спектакль',exact:true})).toBeVisible();
 while(await dialog.getByRole('button',{name:/^Удалить этап /}).count()){
  const buttons=dialog.getByRole('button',{name:/^Удалить этап /});
  const count=await buttons.count();await buttons.first().click();await expect(buttons).toHaveCount(count-1);
 }
 await expect(dialog.getByRole('heading',{name:'Производственный план',exact:true})).toBeVisible();
});

