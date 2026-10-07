import {test,expect} from '@playwright/test';
test.beforeAll(async({request})=>{expect((await request.post('/api/demo')).ok()).toBeTruthy()});
for(const width of [768,1024,1440])test(`Main pages and production controls fit ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});await page.goto('/');
 await expect(page.getByRole('heading',{name:'Поднимем занавес.'})).toBeVisible();
 for(const name of ['Постановки','Сотрудники','Площадки','Оборудование','Сценическая механика','Аналитика','Настройки','Календарь']){
  await page.locator('nav').getByRole('button',{name,exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth),name).toBeLessThanOrEqual(1);
 }
 await page.locator('nav').getByRole('button',{name:'Назначить'}).click();
 await page.getByRole('button',{name:'Проверить и назначить'}).click();
 const dialog=page.getByRole('dialog',{name:'Предварительный план'});await expect(dialog).toBeVisible();
 const rows=dialog.locator('.schedule-row');expect(await rows.count()).toBeGreaterThan(0);
 for(const row of await rows.all()){
  const fits=await row.evaluate(e=>{const r=e.getBoundingClientRect();return Array.from(e.children).every(c=>{const b=c.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1})});expect(fits).toBeTruthy();
 }
 const longName='Очень длинное имя ответственного сотрудника и название профессии';
 await dialog.locator('.personline b').first().evaluate((e,text)=>{e.textContent=text},longName);
 const person=dialog.locator('.personline').first();expect(await person.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBeTruthy();
 await dialog.getByRole('button',{name:'Добавить этап',exact:true}).click();
 const form=dialog.locator('.extra-stage-form');await expect(form).toBeVisible();
 expect(await form.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBeTruthy();
 const footer=dialog.locator('.modal-footer');await expect(footer).toBeInViewport();
});

