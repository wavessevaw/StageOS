import {test,expect} from '@playwright/test';
for(const language of ['ru','en'])test(`Imported resource metadata renders structured facts (${language})`,async({page,request})=>{
 await request.post('/api/demo');
 await request.put('/api/settings/interface',{data:{language}});
 try {
 const name=`Проверка источников ${language}`;
 const res=await request.post('/api/resources',{data:{kind:'Person',name,department:'Звук',data:{qualification:['Звук'],source_urls:['https://example.org/team'],source_positions:['Звукорежиссёр'],source_date:'2026-10-04',team_listing:false,employment_status:'Требует уточнения',evidence:[{production:'Проверочный спектакль',position:'Звукорежиссёр',section:'credits',url:'https://example.org/show'}],additional_details:{nested:{description:'Вложенные сведения',enabled:false},count:12}}}});
 expect(res.ok()).toBeTruthy();
 await page.addInitScript(lang=>localStorage.setItem('stageos-language',lang),language);await page.goto('/');
 await page.getByRole('button',{name:language==='ru'?'Сотрудники':'Staff',exact:true}).click();await page.locator('.resource-card').filter({hasText:name}).click();
 const source=page.getByRole('region',{name:language==='ru'?'Сведения из источников':'Source information',exact:true});await expect(source).toBeVisible();
 await source.locator('summary').filter({hasText:language==='ru'?'Участие в постановках':'Production participation'}).click();
 await expect(source.getByText('Проверочный спектакль',{exact:true})).toBeVisible();await expect(source.getByRole('link',{name:'https://example.org/show'})).toHaveAttribute('href','https://example.org/show');
 await expect(page.getByText('Вложенные сведения',{exact:true})).toBeVisible();await expect(page.locator('body')).not.toContainText('[object Object]');await expect(page.locator('body')).not.toContainText('source_urls');await expect(page.locator('body')).not.toContainText('team_listing');
 } finally {await request.put('/api/settings/interface',{data:{language:'ru'}});}
});
test('Imported production shows credits and eligible people without inventing casts or preparation',async({page,request})=>{
 await request.post('/api/demo');const boot=await(await request.get('/api/bootstrap')).json();const actor=boot.resources.find((r:any)=>r.department==='Артисты');
 const t=await(await request.get('/api/production-template')).json();t.name='Импортированный паспорт для проверки';t.data.roles=[{role:'Главная роль',A:0,B:0,eligible:[actor.id]}];t.data.source_metadata={url:'https://example.org/show',technical_passport_complete:false};t.data.production_credits=[{position:'Режиссёр',people:['Тестовый Постановщик']}];
 expect((await request.post('/api/productions',{data:t})).ok()).toBeTruthy();await page.goto('/');await page.getByRole('button',{name:'Постановки',exact:true}).click();
 const card=page.locator('.production-card').filter({hasText:t.name});await expect(card).toContainText('Подготовка не указана');await expect(card).toContainText('Паспорт требует заполнения');await card.click();
 await expect(page.getByText('Допущенные исполнители · '+actor.name,{exact:true})).toBeVisible();
 await page.getByRole('region',{name:'Сведения из источников'}).locator('summary').click();await expect(page.getByText('Тестовый Постановщик',{exact:true})).toBeVisible();await expect(page.locator('body')).not.toContainText('[object Object]');
});
