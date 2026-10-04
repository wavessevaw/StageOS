import {test,expect} from '@playwright/test';
for(const [index,status] of ['Cancelled','Completed','In Progress'].entries()){
 const oldDate=`2026-10-${20+index}`;const newDate=`2026-12-${21+index}`;
 test(`New event after reviewing ${status} event never inherits its identity`,async({page,request})=>{
  await request.post('/api/demo');
  const boot=await(await request.get('/api/bootstrap')).json();
  const req={production_id:boot.productions[0].id,venue_id:boot.resources.find((r:any)=>r.name==='Большой зал').id,start:oldDate+'T19:00:00',force:true,override_reason:'Исходное событие для проверки истории',notes:'Старое примечание'};
  const plan=await(await request.post('/api/preview',{data:req})).json();
  const response=await request.post('/api/events',{data:{request:req,fingerprint:plan.fingerprint}});
  expect(response.ok()).toBeTruthy();let old=await response.json();
  const steps=status==='Cancelled'?['Cancelled']:['In Preparation','Ready','In Progress',...(status==='Completed'?['Completed']:[])];
  for(const next of steps){const r=await request.post(`/api/events/${old.id}/status`,{data:{status:next,version:old.version}});expect(r.ok()).toBeTruthy();old=await r.json();}
  await page.goto('/');await page.getByRole('button',{name:'Календарь',exact:true}).click();
  await page.getByRole('button',{name:'Месяц',exact:true}).click();
  await page.locator(`.fc-event[data-start="${oldDate}T19:00:00"]`).first().click();
  await page.getByRole('dialog',{name:'Карточка события'}).getByRole('button',{name:'Изменить',exact:true}).click();
  const modal=page.getByRole('dialog',{name:'Предварительный план'});
  await modal.getByLabel('Назначить принудительно с сохранением конфликтов').uncheck();
  await modal.getByLabel('Назначить принудительно с сохранением конфликтов').check();
  await expect(modal.getByLabel('Назначить принудительно с сохранением конфликтов')).toBeEnabled();
  await modal.getByRole('button',{name:'Закрыть Предварительный план'}).click();
  await page.getByRole('button',{name:/^Назначить/}).click();
  await expect(page.getByRole('heading',{name:'Поднимем занавес.'})).toBeVisible();
  await page.getByLabel('Дата',{exact:true}).fill(newDate);
  await page.getByRole('button',{name:'Проверить и назначить',exact:true}).click();
  await expect(modal.getByLabel('Назначить принудительно с сохранением конфликтов')).not.toBeChecked();
  await modal.getByLabel('Назначить принудительно с сохранением конфликтов').check();
  await modal.getByPlaceholder('Обязательная причина, не менее 12 символов').fill('Создаём новый спектакль с известными конфликтами');
  const sent=page.waitForRequest(r=>r.method()==='POST' && new URL(r.url()).pathname==='/api/events');
  await modal.getByRole('button',{name:'Подтвердить',exact:true}).click();
  expect((await sent).postDataJSON().request.event_id).toBeNull();
  await expect(modal).not.toBeVisible();
  const saved=(await(await request.get('/api/events',{maxRetries:2})).json()).filter((e:any)=>e.start.startsWith(newDate));
  expect(saved).toHaveLength(1);expect(saved[0].id).not.toBe(old.id);expect(saved[0].data.request.notes).toBe('');
  const original=await(await request.get(`/api/events/${old.id}`,{maxRetries:2})).json();expect(original.status).toBe(status);expect(original.version).toBe(old.version);
 });
}
