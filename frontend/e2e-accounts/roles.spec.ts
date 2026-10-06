import {test,expect} from '@playwright/test';

test('Planner submits overlaps, artistic director agrees with a recorded reason',async({page})=>{
  const api=async(path:string,body?:any)=>{
    const res=body===undefined?await page.request.get('/api'+path):await page.request.post('/api'+path,{data:body});
    expect(res.ok(),await res.text()).toBeTruthy();return res.json();
  };
  const {id:tid}=await api('/auth/theatres',{theatre_name:'Согласование ролей',name:'Администратор',login:'admin',password:'test-password'});
  const signIn=async(login:string)=>api('/auth/login',{theatre_id:tid,login,password:'test-password'});
  await signIn('admin');
  for(const role of ['editor','artistic_director'])await api('/auth/users',{name:role==='editor'?'Планировщик':'Художественный руководитель',login:role,password:'test-password',role});
  const venue=await api('/venues',{name:'Основная сцена',data:{}});
  const person=await api('/resources',{name:'Артист',kind:'Person',department:'Артисты',data:{qualification:['Артисты']}});
  const template=await api('/production-template');template.name='Спектакль для согласования';template.data.home_venue=venue.id;template.data.roles=[{role:'Главная роль',A:person.id,B:person.id,eligible:[person.id]}];
  const production=await api('/productions',template);
  const request={production_id:production.id,venue_id:venue.id,start:'2026-12-01T18:00:00'};
  const plan=await api('/preview',request);await api('/events',{request,fingerprint:plan.fingerprint});
  await signIn('editor');const proposal=await api('/proposals',request);
  await page.goto('/');await page.getByRole('button',{name:'Уведомления',exact:true}).first().click();
  const row=page.locator('details').filter({hasText:'Спектакль для согласования'});await row.locator('summary').click();
  await expect(row.getByText('Ожидает согласования администратора или художественного руководителя')).toBeVisible();
  await expect(row.getByRole('button',{name:'Согласовать',exact:true})).toHaveCount(0);
  await row.getByRole('button',{name:'Посмотреть предложение'}).click();
  const preview=page.getByRole('dialog',{name:'Предварительный план'});
  await expect(preview.getByRole('button',{name:'Подтвердить',exact:true})).toBeDisabled();
  await expect(preview.getByRole('button',{name:'На согласование',exact:true})).toBeEnabled();
  await expect(preview.getByRole('checkbox',{name:'Назначить принудительно с сохранением конфликтов'})).toHaveCount(0);
  await signIn('artistic_director');await page.reload();await page.getByRole('button',{name:'Уведомления',exact:true}).first().click();
  await row.locator('summary').click();const approve=row.getByRole('button',{name:'Согласовать',exact:true});await expect(approve).toBeDisabled();
  await row.getByLabel('Причина согласования конфликтного назначения').fill('Пересечение согласовано с ответственными');
  if(await row.getByRole('checkbox').count())await row.getByRole('checkbox').check();
  await expect(approve).toBeEnabled();await approve.click();await expect(page.getByText('Предложение согласовано',{exact:true})).toBeVisible();
  const notes=await api('/notifications');expect(notes.find((n:any)=>n.id===proposal.id).data.decision_by.role).toBe('artistic_director');
});
