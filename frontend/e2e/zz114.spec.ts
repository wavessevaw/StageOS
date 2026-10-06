import {test,expect} from '@playwright/test';
test('Imported performance retains passport and eligible cast; calendar titles and colours remain visible',async({page,request})=>{
 await request.post('/api/demo');const b=await(await request.get('/api/bootstrap')).json();const p=b.productions[0];
 const role=p.data.roles.find((r:any)=>r.eligible.length);const actor=b.resources.find((r:any)=>r.id===role.eligible[0]);
 const item={id:990001,title:p.name,production_id:p.id,kind:'Спектакль',status:'Draft',start:'2026-10-16T19:00:00',end:'2026-10-16T21:35:00',health:'WARNING',needs_plan:true,venue:'Большой зал',tasks:[]};
 await page.route('**/api/events**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/api/events')return route.fulfill({json:[item,{...item,id:990002,production_id:p.id+1,title:'Короткий показ из афиши',start:'2026-10-17T18:00:00',end:'2026-10-17T18:15:00'}]});
  if(url.pathname==='/api/events/990001')return route.fulfill({json:{...item,history:[],current:{...item,request:{production_id:p.id},production_passport:p,estimated_end:false,duration_minutes:p.data.duration}}});
  return route.continue();
 });
 await page.goto('/');await page.getByRole('button',{name:'Календарь',exact:true}).first().click();
 const first=page.locator('.fc-event[data-event-id="990001"]');const second=page.locator('.fc-event[data-event-id="990002"]');
 await expect(first).toContainText(p.name);await expect(second).toContainText('Короткий показ из афиши');
 expect(await first.evaluate(el=>getComputedStyle(el).backgroundColor)).not.toBe(await second.evaluate(el=>getComputedStyle(el).backgroundColor));
 expect((await second.boundingBox())!.height).toBeGreaterThanOrEqual(38);
 await first.scrollIntoViewIfNeeded();
 await page.screenshot({path:'../docs/114-calendar.png',fullPage:false});await first.click();
 const modal=page.getByRole('dialog');await expect(modal.getByText(actor.name,{exact:false})).toBeVisible();
 await expect(modal.getByText('Допущенные актёры из паспорта',{exact:true})).toBeVisible();
 await expect(modal.getByText('Это допуск к ролям. Исполнители на эту дату пока не назначены.',{exact:true})).toBeVisible();
 await page.screenshot({path:'../docs/114-imported-passport.png',fullPage:false});
 await modal.getByRole('button',{name:'Открыть паспорт постановки',exact:true}).click();
 await expect(page.getByRole('button',{name:'Редактировать постановку',exact:true})).toBeVisible();
});

test('Production grid handles many long titles with aligned posters and varied colours',async({page,request})=>{
 const b=await(await request.get('/api/bootstrap')).json();const p=b.productions[0];
 for(let i=0;i<12;i++)await request.post('/api/productions/'+p.id+'/clone',{data:{name:'Очень длинное название театральной постановки '+i}});
 await page.goto('/');await page.getByRole('button',{name:'Постановки',exact:true}).first().click();
 const cards=page.locator('.production-card');expect(await cards.count()).toBeGreaterThan(12);
 expect(await cards.evaluateAll(els=>els.every(el=>el.scrollWidth<=el.clientWidth+1))).toBeTruthy();
 const tops=await cards.locator('.poster').evaluateAll(els=>els.slice(0,4).map(el=>el.getBoundingClientRect().top));
 expect(Math.max(...tops)-Math.min(...tops)).toBeLessThan(2);
 const colours=await cards.locator('.poster').evaluateAll(els=>new Set(els.map(el=>getComputedStyle(el).backgroundColor)).size);expect(colours).toBeGreaterThan(7);
 await page.screenshot({path:'../docs/114-production-grid.png',fullPage:false});
});

test('Programme follows all months by default and allows a manual February selection',async({page})=>{
 let config:any={enabled:true,year:2026,months:[10,11,12,1]};let saved:any;
 await page.route('**/api/afisha**',route=>{const path=new URL(route.request().url()).pathname;if(path.endsWith('/settings')){saved=route.request().postDataJSON();config={...config,...saved}}return route.fulfill({json:config})});
 await page.goto('/');await page.getByRole('button',{name:'Календарь',exact:true}).first().click();
 await page.getByRole('button',{name:'Автоимпорт афиши',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Автоимпорт афиши'});const auto=dialog.getByLabel('Все месяцы афиши, включая новые',{exact:true});
 await expect(auto).toBeChecked();await auto.uncheck();await dialog.getByLabel('Февраль 2027',{exact:true}).check();
 await dialog.getByRole('button',{name:'Включить и проверить афишу',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Включить и проверить афишу',exact:true})).toBeEnabled();
 expect(saved.auto_months).toBe(false);expect(saved.months).toContain(2);
 await auto.check();await dialog.getByRole('button',{name:'Включить и проверить афишу',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Включить и проверить афишу',exact:true})).toBeEnabled();expect(saved.auto_months).toBe(true);
});
