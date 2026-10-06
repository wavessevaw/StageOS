import {test,expect} from '@playwright/test';
for(const language of ['ru','en'])test(`Internet tunnel installation, verified address and stop (${language})`,async({page})=>{
 await page.addInitScript(lang=>localStorage.setItem('stageos-language',lang),language);
 const state:any={mode:'server',port:8765,running:true,windows:true,phase:'running',can_manage_tunnel:true,code:'test-connection-code',addresses:['http://127.0.0.1:8765'],logs:[],tunnel:{phase:'stopped',installed:false,can_install:true,saved_key:false,verified:false,url:''}};
 const token='test_fake_authtoken_0123456789';
 await page.route('**/api/connection',route=>route.fulfill({json:state}));
 await page.route('**/api/connection/diagnostics',route=>route.fulfill({json:{http_ok:true}}));
 await page.route('**/api/connection/tunnel',async route=>{
  const body=route.request().postDataJSON();
  if(body.action==='install')state.tunnel.installed=true;
  if(body.action==='start'){expect(body.authtoken).toBe(token);state.tunnel={...state.tunnel,phase:'connected',verified:true,url:'https://test.ngrok.app'};}
  if(body.action==='stop')state.tunnel={...state.tunnel,phase:'stopped',verified:false,url:''};
  await route.fulfill({json:state});
 });
 await page.goto('/');
 const name=(ru:string,en:string)=>language==='ru'?ru:en;
 await page.getByRole('button',{name:name('Настроить подключение','Configure connection'),exact:true}).click();
 await expect(page.getByRole('heading',{name:name('Доступ через Интернет','Internet access')})).toBeVisible();
 await page.getByRole('button',{name:name('Установить ngrok','Install ngrok'),exact:true}).click();
 await expect(page.getByText(name('Проверенный внешний адрес','Verified public address'),{exact:true})).toHaveCount(0);
 await page.getByLabel(name('Authtoken ngrok','ngrok Authtoken'),{exact:true}).fill(token);
 await page.getByRole('button',{name:name('Запустить интернет-туннель','Start Internet tunnel'),exact:true}).click();
 await expect(page.getByLabel(name('Authtoken ngrok','ngrok Authtoken'),{exact:true})).toHaveValue('');
 await expect(page.getByText('https://test.ngrok.app',{exact:true})).toBeVisible();
 await page.screenshot({path:test.info().outputPath(`tunnel-${language}.png`),fullPage:true});
 await page.getByRole('button',{name:name('Остановить туннель','Stop tunnel'),exact:true}).click();
 await expect(page.getByText('https://test.ngrok.app',{exact:true})).toHaveCount(0);
 await expect(page.locator('.server-tunnel')).toContainText(name('Интернет-туннель остановлен','Internet tunnel stopped'));
});
test('StageOS Server → connect with code → sign in → shared changes refresh both computers',async({page,browser})=>{
 const hostContext=await browser.newContext({baseURL:'http://127.0.0.1:8883'});const host=await hostContext.newPage();const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));host.on('pageerror',e=>errors.push(e.message));
 const created=await host.request.post('/api/auth/theatres',{data:{theatre_name:'Общий театр',name:'Администратор сервера',login:'admin',password:'test-password'}});expect(created.ok()).toBeTruthy();const tid=(await created.json()).id;
 expect((await host.request.post('/api/auth/login',{data:{theatre_id:tid,login:'admin',password:'test-password'}})).ok()).toBeTruthy();
 const start=await host.request.post('/api/connection',{data:{mode:'server',port:8885}});expect(start.ok()).toBeTruthy();const code=(await start.json()).code;
 expect((await host.request.get('/api/bootstrap')).ok()).toBeTruthy();
 await host.goto('/');await expect(host.getByRole('button',{name:'Календарь',exact:true})).toBeVisible();
 await page.goto('/');await page.getByRole('button',{name:'Настроить подключение',exact:true}).click();await expect(page.getByRole('heading',{name:'Подключение к общей базе'})).toBeVisible();
 await page.getByRole('button',{name:'Подключиться к серверу',exact:true}).click();await page.screenshot({path:test.info().outputPath('connection.png')});await page.getByLabel('Адрес сервера').fill('127.0.0.1:8885');await page.getByLabel('Код подключения').fill('wrong-code');await page.getByRole('button',{name:'Проверить и подключиться'}).click();await expect(page.getByRole('alert')).toContainText('Неверный код');
 await page.getByLabel('Код подключения').fill(code);await page.getByRole('button',{name:'Проверить и подключиться'}).click();await expect(page.getByRole('heading',{name:'Выберите театр'})).toBeVisible();await expect(page.getByRole('button',{name:'Создать свой театр',exact:true})).toHaveCount(0);
 await page.getByRole('button').filter({hasText:'Общий театр'}).click();await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('test-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('button',{name:'Календарь',exact:true})).toBeVisible();
 await expect(page.locator('.sidebar-bottom')).toContainText('База на сервере');
 await expect(page.locator('.sidebar-bottom')).not.toContainText('Локальная база данных');
 await expect(host.locator('.sidebar-bottom')).toContainText('Общая база · этот сервер');
 await page.getByLabel('Язык приложения').selectOption('en');
 await expect(page.locator('.sidebar-bottom')).toContainText('Database on server');
 await page.getByLabel('Application language').selectOption('ru');
 const users=await (await host.request.get('/api/connection')).json();
 expect(users.users.online).toBe(1);expect(users.users.items[0].login).toBe('admin');
 await page.getByRole('button',{name:'Сотрудники',exact:true}).click();await host.getByRole('button',{name:'Сотрудники',exact:true}).click();
 await host.getByRole('button',{name:'Добавить сотрудника'}).click();await host.getByLabel('Название / ФИО').fill('Сотрудник с сервера');await host.getByLabel('Подразделение',{exact:true}).fill('Артисты');await host.getByRole('button',{name:'Сохранить ресурс'}).click();
 await expect(page.locator('.resource-card').filter({hasText:'Сотрудник с сервера'})).toBeVisible({timeout:15000});
 await page.getByRole('button',{name:'Добавить сотрудника'}).click();await page.getByLabel('Название / ФИО').fill('Сотрудник с клиента');await page.getByLabel('Подразделение',{exact:true}).fill('Артисты');await page.getByRole('button',{name:'Сохранить ресурс'}).click();
 await expect(host.locator('.resource-card').filter({hasText:'Сотрудник с клиента'})).toBeVisible({timeout:15000});
 await page.getByRole('button',{name:'Личный аккаунт'}).click();await page.getByRole('button',{name:'Выйти из аккаунта',exact:true}).click();await expect(page.getByRole('heading',{name:'Выберите театр'})).toBeVisible();expect((await host.request.get('/api/bootstrap')).ok()).toBeTruthy();
 await host.getByRole('button',{name:'Личный аккаунт'}).click();await host.getByRole('button',{name:'Подключение к серверу',exact:true}).click();await expect(host.getByText('Сервер работает',{exact:true})).toBeVisible();await host.screenshot({path:test.info().outputPath('server.png')});
 await expect(host.locator('.server-users')).toContainText('Активных сетевых пользователей нет');
 // Drop the actual LAN listener while the client is signed in and idle.
 expect((await page.request.post('/api/auth/login',{data:{theatre_id:tid,login:'admin',password:'test-password'}})).ok()).toBeTruthy();
 await page.reload();await expect(page.getByRole('button',{name:'Календарь',exact:true})).toBeVisible();
 expect((await host.request.post('/api/connection',{data:{mode:'local'}})).ok()).toBeTruthy();
 await expect(page.getByRole('heading',{name:'Вход в аккаунт',exact:true})).toBeVisible({timeout:15000});
 await expect(page.getByRole('button',{name:'Календарь',exact:true})).toHaveCount(0);
 await expect(page.getByRole('alert')).toContainText('Связь с сервером потеряна');
 await expect(page.getByLabel('Пароль',{exact:true})).toHaveValue('');
 const restarted=await host.request.post('/api/connection',{data:{mode:'server',port:8885}});expect(restarted.ok()).toBeTruthy();
 expect((await page.request.get('/api/auth/session')).status()).toBe(503); // the restarted host has a new connection code
 await page.getByRole('button',{name:'Настроить подключение',exact:true}).click();
 await page.getByLabel('Код подключения').fill((await restarted.json()).code);
 await page.getByRole('button',{name:'Проверить и подключиться'}).click();
 await page.getByRole('button').filter({hasText:'Общий театр'}).click();
 await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('test-password');
 await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('button',{name:'Календарь',exact:true})).toBeVisible();
 expect(errors).toEqual([]);await hostContext.close();
});
test('Connection screen is translated into English',async({page})=>{await page.goto('/');await page.getByLabel('Язык приложения').selectOption('en');await page.getByRole('button',{name:'Configure connection'}).click();await expect(page.getByRole('heading',{name:'Connect to a shared database'})).toBeVisible();await expect(page.getByRole('button',{name:'Connect to a server',exact:true})).toBeVisible()});


test('Server status, HTTP check and journal remain visible after repeated start',async({browser})=>{
 const context=await browser.newContext({baseURL:'http://127.0.0.1:8883'});
 const page=await context.newPage();
 const theatres=await (await context.request.get('/api/auth/theatres')).json();
 expect((await context.request.post('/api/auth/login',{data:{theatre_id:theatres.theatres[0].id,login:'admin',password:'test-password'}})).ok()).toBeTruthy();
 await page.goto('/');
 await expect(page.locator('.server-indicator')).toContainText('Сервер работает');
 await page.locator('.server-indicator').click();
 await expect(page.locator('.server-live')).toContainText('Сервер работает');
 await expect(page.getByText('HTTP: отвечает',{exact:true})).toBeVisible();
 await expect(page.getByRole('log')).toContainText('сервер отвечает');
 await page.getByRole('button',{name:'Сервер запущен · проверить'}).click();
 await expect(page.getByRole('log')).toContainText('Повторный запуск не требуется');
 expect((await context.request.get('/api/bootstrap')).ok()).toBeTruthy();
 await page.locator('.connection-panel').evaluate(el=>el.scrollTop=0);
 await page.screenshot({path:test.info().outputPath('server-status.png'),fullPage:true});
 await context.close();
});


test('Windows setup shows progress and separates public network from firewall success',async({browser})=>{
 const context=await browser.newContext({baseURL:'http://127.0.0.1:8883'});const page=await context.newPage();
 const theatres=await (await context.request.get('/api/auth/theatres')).json();
 await context.request.post('/api/auth/login',{data:{theatre_id:theatres.theatres[0].id,login:'admin',password:'test-password'}});
 let configured=false;
 // Windows-only UI states; real PowerShell is covered separately on Windows.
 await page.route('**/api/connection',async route=>{const response=await route.fetch();const s=await response.json();await route.fulfill({json:{...s,windows:true,diagnostics:{...s.diagnostics,firewall:configured?'allowed':'missing',profiles:[{index:7,interface:'Ethernet',name:'Театр',category:configured?'Private':'Public'}]}}})});
 await page.route('**/api/connection/firewall',async route=>{expect(route.request().postDataJSON().interface_index).toBe(7);await new Promise(r=>setTimeout(r,700));configured=true;await route.fulfill({json:{ok:true,message:'Настройка Windows завершена'}})});
 await page.goto('/');await page.locator('.server-indicator').click();
 await expect(page.getByText('Правило не создано',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Доверенная локальная сеть')).toHaveValue('7');
 await page.getByRole('button',{name:'Настроить Windows',exact:true}).click();
 await expect(page.locator('.server-progress')).toContainText('Подтвердите запрос Windows');
 await expect(page.getByText('Правило разрешает подключения',{exact:true})).toBeVisible();
 await expect(page.locator('.server-checks')).toContainText('Частная');
 await context.close();
});
