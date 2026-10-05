import {test,expect} from '@playwright/test';
test('Editable stages and individual event actors persist into calendar',async({page,request})=>{
 await page.goto('/');
 await expect(page.getByRole('button',{name:'Создать демонстрационный театр'}).or(page.getByRole('heading',{name:'Поднимем занавес.'}))).toBeVisible({timeout:60000});
 if(await page.getByRole('button',{name:'Создать демонстрационный театр'}).isVisible())await page.getByRole('button',{name:'Создать демонстрационный театр'}).click();
 await expect(page.getByRole('heading',{name:'Поднимем занавес.'})).toBeVisible({timeout:60000});
 await page.getByLabel('Дата',{exact:true}).fill('2027-01-18');
 await page.getByRole('button',{name:'Проверить и назначить'}).click();
 const dialog=page.getByRole('dialog',{name:'Предварительный план'});await expect(dialog).toBeVisible();
 const actor=dialog.locator('.event-role-row select').first();const original=await actor.inputValue();
 const options=await actor.locator('option').evaluateAll(nodes=>nodes.map(n=>({value:(n as HTMLOptionElement).value,text:n.textContent||''})));
 const alternative=options.find(o=>o.value&&o.value!==original&&!o.text.includes('требуется допуск'));expect(alternative).toBeTruthy();
 await actor.selectOption(alternative!.value);await expect(actor).toHaveValue(alternative!.value);
 await dialog.getByRole('button',{name:'Удалить этап Погрузка',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Восстановить: Погрузка'})).toBeVisible();
 await expect(dialog.getByRole('button',{name:'Удалить этап Погрузка',exact:true})).toHaveCount(0);
 const departureDuration=dialog.getByLabel('Длительность Выезд',{exact:true});const previousDuration=await departureDuration.inputValue();
 await departureDuration.fill('0');await dialog.getByRole('heading',{name:'Производственный план',exact:true}).click();await expect(departureDuration).toHaveValue(previousDuration);
 await dialog.getByLabel('Начало Спектакль',{exact:true}).fill('2027-01-19T19:00');
 await dialog.getByRole('heading',{name:'Производственный план',exact:true}).click();
 await expect(dialog.getByLabel('Начало Спектакль',{exact:true})).toHaveValue('2027-01-19T19:00');
 await dialog.getByRole('button',{name:'Добавить этап',exact:true}).click();
 await expect(dialog.getByLabel('Начало нового этапа')).toHaveValue('2027-01-19T18:30');
 await dialog.getByLabel('Название этапа',{exact:true}).fill('Проверка реквизита');
 await dialog.getByLabel('Подразделение этапа').selectOption('Реквизит');
 await dialog.getByLabel('Начало нового этапа').fill('2027-01-19T18:20');
 await dialog.getByRole('button',{name:'Добавить в план и проверить'}).click();
 await expect(dialog.getByRole('button',{name:'Удалить этап Проверка реквизита',exact:true})).toBeVisible();
 await dialog.getByRole('button',{name:'Подтвердить',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Календарь',exact:true})).toBeVisible();
 const card=page.locator('.fc-event[data-start="2027-01-19T19:00:00"]').first();await expect(card).toBeVisible();await card.click();
 const detail=page.getByRole('dialog',{name:'Карточка события'});await expect(detail.getByText('Проверка реквизита',{exact:true}).first()).toBeVisible();
 await detail.getByRole('button',{name:'Производство',exact:true}).click();
 await expect(page.getByText('Проверка реквизита',{exact:true}).first()).toBeVisible();
});

test('Confirmed history offers a reviewed plan without saving it',async({page,request})=>{
 const boot=(await request.get('/api/bootstrap')).json();const b=await boot;
 const venue=b.resources.find((x:any)=>x.name==='Большой зал');
 for(const day of ['02','04']){
  const r={production_id:1,venue_id:venue.id,start:`2027-02-${day}T19:00:00`,cast:'B',removed_tasks:['Погрузка']};
  const p=await request.post('/api/preview',{data:r});expect(p.ok()).toBeTruthy();
  const saved=await request.post('/api/events',{data:{request:r,fingerprint:(await p.json()).fingerprint}});expect(saved.ok()).toBeTruthy();
 }
 const before=(await (await request.get('/api/events')).json()).length;
 await page.goto('/');await expect(page.getByRole('heading',{name:'Поднимем занавес.'})).toBeVisible();
 await page.getByLabel('Дата',{exact:true}).fill('2027-02-06');
 await expect(page.getByRole('button',{name:'Посмотреть предложение'}).first()).toBeVisible({timeout:15000});
 await page.getByRole('button',{name:'Посмотреть предложение'}).first().click();
 const dialog=page.getByRole('dialog',{name:'Предварительный план'});await expect(dialog).toBeVisible();
 await expect(dialog.getByRole('button',{name:'Восстановить: Погрузка'})).toBeVisible();
 expect((await (await request.get('/api/events')).json()).length).toBe(before);
});
