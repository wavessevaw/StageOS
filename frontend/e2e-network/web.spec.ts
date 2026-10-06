import {test,expect} from '@playwright/test';

test('Browser enters connection code, signs in and uses the shared server without a desktop gateway',async({browser})=>{
  test.setTimeout(150000);
  const host=await browser.newContext({baseURL:'http://127.0.0.1:8883'});
  const theatres=await (await host.request.get('/api/auth/theatres')).json();
  const tid=theatres.theatres[0].id;
  expect((await host.request.post('/api/auth/login',{data:{theatre_id:tid,login:'admin',password:'test-password'}})).ok()).toBeTruthy();
  const status=await (await host.request.get('/api/connection')).json();
  const web=await browser.newContext({baseURL:'http://127.0.0.1:8885'});const page=await web.newPage();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await expect(page.getByRole('heading',{name:'Подключение через браузер'})).toBeVisible();
  await page.getByLabel('Код подключения',{exact:true}).fill('incorrect-code');await page.getByRole('button',{name:'Проверить код и продолжить'}).click();
  await expect(page.getByRole('alert')).toContainText('Неверный код');await expect(page.getByRole('heading',{name:'Подключение через браузер'})).toBeVisible();
  await page.getByLabel('Код подключения',{exact:true}).fill(status.code);await page.getByRole('button',{name:'Проверить код и продолжить'}).click();
  await expect(page.getByRole('heading',{name:'Выберите театр'})).toBeVisible();await expect(page.getByRole('button',{name:'Создать свой театр',exact:true})).toHaveCount(0);
  await page.getByRole('button').filter({hasText:'Общий театр'}).click();await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('test-password');await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page.getByRole('button',{name:'Календарь',exact:true})).toBeVisible();await expect(page.locator('.sidebar-bottom')).toContainText('База на сервере');
  await page.getByRole('button',{name:'Сотрудники',exact:true}).click();await expect(page.locator('.resource-card').filter({hasText:'Сотрудник с клиента'})).toBeVisible();
  // Simulate network loss at the browser boundary; LAN loss is covered separately.
  await page.route('**/api/auth/session',route=>route.fulfill({status:503,contentType:'text/html',body:'<h1>Tunnel unavailable</h1>'}));
  await expect(page.getByRole('heading',{name:'Вход в аккаунт'})).toBeVisible({timeout:70000});await expect(page.getByLabel('Пароль',{exact:true})).toHaveValue('');
  await page.unroute('**/api/auth/session');await page.reload();await expect(page.getByRole('button',{name:'Календарь',exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);await web.close();await host.close();
});
