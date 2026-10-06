import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
test('English switch persists in database and exports real PDF and PNG',async({page,request})=>{
  test.setTimeout(60000);page.setDefaultTimeout(10000);
  await request.post('/api/demo');await page.goto('/');
  try{
    await page.getByLabel('Язык приложения',{exact:true}).selectOption('en');
    await expect(page.getByRole('button',{name:/^Calendar$/})).toBeVisible();
    await page.evaluate(()=>localStorage.clear());await page.reload();
    await expect(page.getByLabel('Application language',{exact:true})).toHaveValue('en');
    expect((await(await request.get('/api/bootstrap')).json()).language).toBe('en');
    await page.getByRole('button',{name:'Calendar',exact:true}).click();
    await page.getByRole('button',{name:'Export schedule',exact:true}).click();
    const modal=page.getByRole('dialog',{name:'Export schedule',exact:true});
    await modal.getByLabel('Period starts',{exact:true}).fill('2026-10-16');
    await modal.getByLabel('Period ends',{exact:true}).fill('2026-10-16');
    const [pdf]=await Promise.all([page.waitForEvent('download',{timeout:15000}),modal.getByRole('button',{name:'Download schedule',exact:true}).click()]);
    const bytes=await readFile((await pdf.path())!);expect(bytes.subarray(0,5).toString()).toBe('%PDF-');
    await modal.getByLabel('File format',{exact:true}).selectOption('png');
    const [png]=await Promise.all([page.waitForEvent('download',{timeout:15000}),modal.getByRole('button',{name:'Download schedule',exact:true}).click()]);
    const image=await readFile((await png.path())!);
    expect(image.subarray(0,2).toString('hex')==='504b' || image.subarray(0,8).toString('hex')==='89504e470d0a1a0a').toBeTruthy();
    await modal.getByRole('button',{name:'Close',exact:true}).click();
    await page.getByRole('button',{name:'StageOS Assistant',exact:true}).click();
    await page.getByRole('textbox').last().fill('What happens today?');
    await page.getByRole('button',{name:'Ask',exact:true}).click();
    await expect(page.locator('.answer')).toContainText('Asia/Vladivostok');
    await expect(page.locator('.answer')).toContainText('Scope:');
  }finally{await page.request.put('/api/settings/interface',{data:{language:'ru'}}).catch(()=>{});await page.evaluate(()=>localStorage.setItem('stageos-language','ru')).catch(()=>{});}
});
