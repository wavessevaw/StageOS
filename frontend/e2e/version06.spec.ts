import { test, expect } from '@playwright/test';

test.beforeAll(async ({ request }) => { await request.post('/api/demo'); });

test('Third appointment offers morning preparation across different casts and curtain times', async ({ page, request }) => {
  const boot = await (await request.get('/api/bootstrap')).json();
  const venue = boot.resources.find((x: any) => x.name === 'Большой зал');
  for (const [day, cast, show] of [['01', 'A', '19:00'], ['03', 'B', '18:00']]) {
    const start = `2027-05-${day}`;
    const r = { production_id: 1, venue_id: venue.id, start: `${start}T${show}:00`, cast, run_through: true,
      task_overrides: Object.fromEntries([
        ...['Монтаж сцены', 'Световой монтаж', 'Звуковой монтаж', 'Видеомонтаж'].map(n => [n, { start: `${start}T09:00:00`, duration: 60 }]),
        ['Orchestra setup', { start: `${start}T09:00:00`, duration: 30 }], ['Technical Check', { duration: 15 }], ['RF check', { duration: 15 }],
      ]) };
    const response = await request.post('/api/preview', { data: r });
    expect(response.ok()).toBeTruthy();
    const plan = await response.json();
    const saved = await request.post('/api/events', { data: { request: r, fingerprint: plan.fingerprint } });
    expect(saved.ok(), await saved.text()).toBeTruthy();
  }
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Поднимем занавес.' })).toBeVisible();
  await page.getByLabel('Дата', { exact: true }).fill('2027-05-05');
  const suggestion = page.locator('.suggestion-options > div').filter({ hasText: 'Организационный план' }).first();
  await expect(suggestion).toBeVisible();
  await suggestion.getByText('Этапы предложенного плана', { exact: true }).click();
  await expect(suggestion.getByText('09:00–09:30 · Подготовка оркестра', { exact: true })).toBeVisible();
  await suggestion.getByRole('button', { name: 'Посмотреть предложение' }).click();
  const modal = page.getByRole('dialog', { name: 'Предварительный план' });
  const orchestra = modal.getByLabel('Начало Orchestra setup', { exact: true });
  await expect(orchestra).toHaveValue('2027-05-05T09:00');
  await orchestra.fill('2027-05-05T08:50');
  await modal.getByRole('heading', { name: 'Производственный план', exact: true }).click();
  await expect(orchestra).toHaveValue('2027-05-05T08:50');
  await modal.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Календарь', exact: true })).toBeVisible();
  const events = await (await request.get('/api/events')).json();
  const saved = events.find((e: any) => e.start === '2027-05-05T19:00:00');
  expect(saved).toBeTruthy();
  const detail = await (await request.get(`/api/events/${saved.id}`)).json();
  expect(detail.current.tasks.find((t: any) => t.name === 'Orchestra setup').start).toBe('2027-05-05T08:50:00');
  expect(detail.current.conflicts.some((c: any) => c.code === 'long_shift')).toBeFalsy();
});

test('Export reports selected destination, cancellation and browser downloads', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Календарь', exact: true }).click();
  await page.getByRole('button', { name: 'Экспорт расписания', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Экспорт расписания' });
  await modal.getByLabel('Начало периода', { exact: true }).fill('2027-05-05');
  await modal.getByLabel('Конец периода', { exact: true }).fill('2027-05-05');
  await page.evaluate(() => {
    (window as any).pywebview = { api: { save_file: async (name: string, encoded: string) => {
      if (!atob(encoded).startsWith('%PDF-')) throw new Error('PDF signature missing');
      return { status: 'saved', path: 'C:\\Расписания\\' + name };
    } } };
  });
  await modal.getByRole('button', { name: 'Скачать расписание', exact: true }).click();
  await expect(modal.getByRole('status')).toContainText('Файл сохранён: C:\\Расписания\\');
  await page.evaluate(() => { (window as any).pywebview.api.save_file = async () => ({ status: 'cancelled' }); });
  await modal.getByRole('button', { name: 'Скачать расписание', exact: true }).click();
  await expect(modal.getByRole('status')).toHaveText('Сохранение отменено');
  await page.evaluate(() => { delete (window as any).pywebview; });
  const downloaded = page.waitForEvent('download');
  await modal.getByRole('button', { name: 'Скачать расписание', exact: true }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/\.pdf$/);
  await expect(modal.getByRole('status')).toContainText('Ctrl+J');
});

test('Model response check shows success and actionable failure', async ({ page, request }) => {
  const original = await (await request.get('/api/settings/llm')).json();
  try {
    await request.put('/api/settings/llm', { data: { enabled: true, provider: 'Ollama', endpoint: 'http://127.0.0.1:11434/v1', model: 'qwen3:0.6b' } });
    await page.route('**/api/settings/llm/test', route => route.fulfill({ json: { status: 'Connected', selected_model_available: true, generation: 'PASS' } }));
    await page.goto('/');
    await page.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.getByRole('button', { name: 'Проверить ответ модели', exact: true }).click();
    await expect(page.getByText('Модель ответила. Генерация и разбор ответа проверены.', { exact: true })).toBeVisible();
    await page.unroute('**/api/settings/llm/test');
    await page.route('**/api/settings/llm/test', route => route.fulfill({ status: 502, json: { detail: 'Модель вернула пустой ответ' } }));
    await page.getByRole('button', { name: 'Проверить ответ модели', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Модель вернула пустой ответ' })).toBeVisible();
  } finally { await request.put('/api/settings/llm', { data: original }); }
});
