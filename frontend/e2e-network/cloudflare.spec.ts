import {test,expect} from '@playwright/test';
for(const language of ['ru','en'])test(`Cloudflare Quick Tunnel without token, verified address and provider switch (${language})`,async({page})=>{
 await page.addInitScript(lang=>localStorage.setItem('stageos-language',lang),language);
 const state:any={mode:'server',port:8765,running:true,windows:true,phase:'running',can_manage_tunnel:true,code:'test-connection-code',addresses:['http://127.0.0.1:8765'],logs:[],tunnel:{provider:'cloudflare',phase:'stopped',installed:false,can_install:true,saved_key:false,verified:false,url:''}};
 await page.route('**/api/connection',route=>route.fulfill({json:state}));await page.route('**/api/connection/diagnostics',route=>route.fulfill({json:{http_ok:true}}));
 await page.route('**/api/connection/tunnel',async route=>{const body=route.request().postDataJSON();
  if(body.action==='install')state.tunnel.installed=true;
  if(body.action==='start'){expect(body.protocol).toBe('http2');expect(body.authtoken).toBeUndefined();state.tunnel={...state.tunnel,phase:'connected',verified:true,url:'https://stageos-test.trycloudflare.com'}}
  if(body.action==='stop')state.tunnel={...state.tunnel,phase:'stopped',verified:false,url:''};
  if(body.action==='select')state.tunnel={...state.tunnel,provider:body.provider};
  await route.fulfill({json:state});
 });
 const name=(ru:string,en:string)=>language==='ru'?ru:en;
 await page.goto('/');await page.getByRole('button',{name:name('Настроить подключение','Configure connection'),exact:true}).click();
 await expect(page.getByLabel(name('Сервис туннеля','Tunnel service'))).toHaveValue('cloudflare');
 await page.getByRole('button',{name:name('Установить Cloudflare','Install Cloudflare'),exact:true}).click();
 await expect(page.getByLabel(name('Authtoken ngrok','ngrok Authtoken'),{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:name('Запустить интернет-туннель','Start Internet tunnel'),exact:true})).toBeEnabled();
 await page.getByRole('button',{name:name('Запустить интернет-туннель','Start Internet tunnel'),exact:true}).click();
 await expect(page.getByText('https://stageos-test.trycloudflare.com',{exact:true})).toBeVisible();
 await expect(page.getByLabel(name('Сервис туннеля','Tunnel service'))).toBeDisabled();
 const panel=page.locator('.server-tunnel');expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await page.screenshot({path:test.info().outputPath(`cloudflare-${language}.png`),fullPage:true});
 await page.getByRole('button',{name:name('Остановить туннель','Stop tunnel'),exact:true}).click();await expect(page.getByText('https://stageos-test.trycloudflare.com',{exact:true})).toHaveCount(0);
 await page.getByLabel(name('Сервис туннеля','Tunnel service')).selectOption('ngrok');await expect(page.getByLabel(name('Authtoken ngrok','ngrok Authtoken'),{exact:true})).toBeVisible();
});
