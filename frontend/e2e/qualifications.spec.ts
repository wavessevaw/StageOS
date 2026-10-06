import {test,expect} from '@playwright/test';
test('Employee has explicit additional qualifications, retained on save',async({page,request})=>{
 await request.post('/api/demo');await page.goto('/');
 await page.getByRole('button',{name:'Сотрудники',exact:true}).click();
 await page.getByRole('button',{name:'Добавить сотрудника',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Редактор ресурса'});
 await dialog.getByLabel('Название / ФИО',{exact:true}).fill('Тестовый артист режиссёр');
 await dialog.getByLabel('Подразделение',{exact:true}).fill('Артисты');
 await dialog.getByLabel('Квалификация Режиссёр',{exact:true}).check();
 await expect(dialog.getByLabel('Квалификация Звук',{exact:true})).not.toBeChecked();
 await dialog.getByRole('button',{name:'Сохранить ресурс',exact:true}).click();
 await expect(dialog).not.toBeVisible();
 const boot=await(await request.get('/api/bootstrap')).json();
 const employee=boot.resources.find((r:any)=>r.name==='Тестовый артист режиссёр');
 expect(employee.department).toBe('Артисты');
 expect(employee.data.qualification).toContain('Артисты');
 expect(employee.data.qualification).toContain('Режиссёр');
 expect(employee.data.qualification).not.toContain('Звук');
});

test('Unused qualification can be created and deleted through the manager',async({page,request})=>{
 await request.post('/api/demo');await page.goto('/');
 await page.getByRole('button',{name:'Настройки',exact:true}).click();
 await page.getByRole('button',{name:'Управление квалификациями',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Управление квалификациями'});
 await dialog.getByLabel('Новая квалификация',{exact:true}).fill('Тестовая квалификация');
 await dialog.getByRole('button',{name:'Добавить',exact:true}).click();
 const row=dialog.locator('.personline').filter({hasText:'Тестовая квалификация'});
 await expect(row).toBeVisible();
 await row.getByRole('button',{name:'Удалить',exact:true}).click();
 await expect(row).toHaveCount(0);
 const used=dialog.locator('.personline').filter({has:page.getByText('Артисты',{exact:true})});
 await expect(used.getByRole('button',{name:'Удалить',exact:true})).toBeDisabled();
});
