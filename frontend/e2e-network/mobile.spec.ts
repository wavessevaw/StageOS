import {test,expect} from '@playwright/test';

test('Phone signs in without connection code, sees only its own weekly assignments and reconnects by login',async({browser})=>{
  test.setTimeout(180000);
  const host=await browser.newContext({baseURL:'http://127.0.0.1:8883'});
  const created=await host.request.post('/api/auth/theatres',{data:{theatre_name:'Я мобильный театр',name:'Администратор',login:'mobile-admin',password:'test-password'}});expect(created.ok()).toBeTruthy();
  const tid=(await created.json()).id;
  expect((await host.request.post('/api/auth/login',{data:{theatre_id:tid,login:'mobile-admin',password:'test-password'}})).ok()).toBeTruthy();
  expect((await host.request.post('/api/auth/users',{data:{name:'Василиса Серова',login:'Василиса Серова',password:'test-password',role:'viewer'}})).ok()).toBeTruthy();
  const person=await (await host.request.post('/api/resources',{data:{kind:'Person',name:'Василиса Серова',department:'Артисты',data:{qualification:['Артисты']}}})).json();
  const other=await (await host.request.post('/api/resources',{data:{kind:'Person',name:'Чужой сотрудник',department:'Артисты',data:{qualification:['Артисты']}}})).json();
  const venue=await (await host.request.post('/api/venues',{data:{name:'Мобильная сцена',data:{}}})).json();
  const today=new Date();today.setHours(18,0,0,0);
  const date=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  for(const [cast,title,offset] of [[person,'Мой спектакль',0],[other,'Чужой спектакль',1]] as const){
    const template=await (await host.request.get('/api/production-template')).json();template.name=title;template.data.home_venue=venue.id;template.data.roles=[{role:'Главная роль',A:cast.id,B:cast.id,eligible:[cast.id]}];
    const production=await (await host.request.post('/api/productions',{data:template})).json();
    const d=new Date(today);d.setDate(d.getDate()+offset);const eventDate=offset?`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`:date;
    const request={production_id:production.id,venue_id:venue.id,start:eventDate+'T18:00:00',override_reason:'Назначение для проверки личного расписания',force:true};
    const plan=await (await host.request.post('/api/preview',{data:request})).json();
    const saved=await host.request.post('/api/events',{data:{request,fingerprint:plan.fingerprint}});expect(saved.ok(),await saved.text()).toBeTruthy();
  }
  expect((await host.request.post('/api/connection',{data:{mode:'server',port:8886}})).ok()).toBeTruthy();
  const phone=await browser.newContext({baseURL:'http://127.0.0.1:8886',viewport:{width:390,height:844},isMobile:true,hasTouch:true});const page=await phone.newPage();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await expect(page.getByRole('heading',{name:'Вход в личное расписание'})).toBeVisible();
  await expect(page.getByLabel('Код подключения',{exact:true})).toHaveCount(0);
  await page.getByLabel('Логин',{exact:true}).fill('Василиса Серова');await page.getByLabel('Пароль',{exact:true}).fill('wrong-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Неверный');
  await page.getByLabel('Пароль',{exact:true}).fill('test-password');await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Василиса Серова',exact:true})).toBeVisible();await expect(page.locator('.mobile-day')).toHaveCount(7);
  await expect(page.getByRole('heading',{name:'Мой спектакль'})).toBeVisible();await expect(page.getByText('Чужой спектакль',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Создать событие',exact:true})).toHaveCount(0);expect((await phone.request.get('/api/bootstrap')).status()).toBe(403);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();expect(await page.locator('.mobile-app > main').evaluate(el=>el.getBoundingClientRect().width)).toBeGreaterThan(290);
  await page.screenshot({path:test.info().outputPath('personal-mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'Следующая неделя'}).click();await expect(page.getByRole('heading',{name:'Мой спектакль'})).toHaveCount(0);await page.getByRole('button',{name:'Текущая неделя'}).click();await expect(page.getByRole('heading',{name:'Мой спектакль'})).toBeVisible();
  let brief=0;
  await page.route('**/api/mobile/**',route=>{brief++;return brief<=3?route.fulfill({status:503,contentType:'text/html',body:'Temporary network loss'}):route.continue()});
  await page.getByRole('button',{name:'Следующая неделя'}).click();
  await expect(page.getByRole('heading',{name:'Восстанавливаем связь с сервером'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Восстанавливаем связь с сервером'})).toHaveCount(0,{timeout:16000});
  await expect(page.getByRole('heading',{name:'Василиса Серова',exact:true})).toBeVisible();
  await page.unroute('**/api/mobile/**');await page.getByRole('button',{name:'Текущая неделя'}).click();await expect(page.getByRole('heading',{name:'Мой спектакль'})).toBeVisible();
  await page.route('**/api/mobile/**',route=>route.fulfill({status:503,contentType:'text/html',body:'<h1>Tunnel unavailable</h1>'}));
  await expect(page.getByRole('heading',{name:'Вход в личное расписание'})).toBeVisible({timeout:70000});await expect(page.getByLabel('Пароль',{exact:true})).toHaveValue('');
  await page.unroute('**/api/mobile/**');await page.reload();await expect(page.getByRole('heading',{name:'Вход в личное расписание'})).toBeVisible();
  await page.getByLabel('Логин',{exact:true}).fill('Василиса Серова');await page.getByLabel('Пароль',{exact:true}).fill('test-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('heading',{name:'Мой спектакль'})).toBeVisible();
  await page.setViewportSize({width:320,height:700});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();expect(await page.locator('.mobile-app > main').evaluate(el=>el.getBoundingClientRect().width)).toBeGreaterThan(290);
  await page.getByLabel('Язык приложения').selectOption('en');await expect(page.getByRole('button',{name:'Current week'})).toBeVisible();await page.getByRole('button',{name:'Sign out',exact:true}).click();
  expect(errors).toEqual([]);await phone.close();await host.close();
});


