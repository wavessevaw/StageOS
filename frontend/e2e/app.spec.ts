import { test, expect } from "@playwright/test";
test.describe("StageOS integration", () => {
  test("First run → Предварительный план → confirm → calendar → detail → production", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/");
    await expect(
      page
        .getByRole("button", { name: "Создать демонстрационный театр" })
        .or(page.getByRole("heading", { name: "Поднимем занавес." })),
    ).toBeVisible();
    if (
      await page
        .getByRole("button", { name: "Создать демонстрационный театр" })
        .isVisible()
    )
      await page
        .getByRole("button", { name: "Создать демонстрационный театр" })
        .click();
    await expect(
      page.getByRole("heading", { name: "Поднимем занавес." }),
    ).toBeVisible({ timeout: 60000 });
    await expect(
      page.getByRole("button", { name: "Проверить и назначить" }),
    ).toBeEnabled();
    await page.screenshot({ path: "../docs/01-assign.png", fullPage: true });
    await page.getByRole("button", { name: "Проверить и назначить" }).click();
    const dialog = page.getByRole("dialog", { name: "Предварительный план" });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText("Полная версия", { exact: true }),
    ).toBeVisible();
    await page.screenshot({ path: "../docs/02-preview.png" });
    const reason=dialog.getByLabel("Обоснование решения администратора или художественного руководителя");
    if(await reason.count())await reason.fill("Ранний монтаж согласован с площадкой");
    await dialog
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Календарь", exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(".fc-event").filter({ hasText: "Северный ветер" }).first(),
    ).toBeVisible({ timeout: 60000 });
    await page.locator('.fc-event[data-start="2026-10-16T19:00:00"]').click();
    const detail = page.getByRole("dialog", { name: "Карточка события" });
    await expect(
      detail.getByRole("heading", { name: "Ответственные и состав" }),
    ).toBeVisible();
    await expect(
      detail.locator("summary").filter({ hasText: "Оркестр" }).first(),
    ).toBeVisible();
    await expect(
      detail.getByText("Техническая проверка", { exact: true }).first(),
    ).toBeVisible();
    await detail.getByRole("button", { name: "Производство" }).click();
    await expect(
      page.getByText("Световой монтаж", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "../docs/03-production.png",
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
  test("Day, week, month, filters and resource calendars", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Календарь", exact: true }).click();
    await page.getByRole("button", { name: "Месяц", exact: true }).click();
    await expect(page.locator(".fc-dayGridMonth-view")).toBeVisible();
    await page.getByRole("button", { name: "День", exact: true }).click();
    await expect(page.locator(".fc-timeGridDay-view")).toBeVisible();
    await page.getByLabel("Подготовка и выезды").check();
    await expect(
      page.locator(".fc-event[data-event-id^=task-]").first(),
    ).toBeVisible();
    await page.getByLabel("Подготовка и выезды").uncheck();
    await page.getByRole("button", { name: "Неделя", exact: true }).click();
    await expect(page.locator(".fc-timeGridWeek-view")).toBeVisible();
    await page
      .getByLabel("Фильтр Площадка")
      .selectOption({ label: "Камерный зал" });
    await expect(page.locator(".cal-loading")).toBeHidden({ timeout: 60000 });
    await expect(
      page.locator(".fc-event").filter({ hasText: "Северный ветер" }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Сотрудники", exact: true }).click();
    await page.locator(".resource-card").first().click();
    await page.getByRole("button", { name: "Показать в календаре" }).click();
    await expect(page.getByLabel("Фильтр Сотрудник")).not.toHaveValue("");
    await page.getByRole("button", { name: "Площадки", exact: true }).click();
    await page
      .locator(".resource-card")
      .filter({ hasText: "Большой зал" })
      .click();
    await page.getByRole("button", { name: "Показать в календаре" }).click();
    await expect(page.getByLabel("Фильтр Площадка")).not.toHaveValue("");
    await page
      .getByRole("button", { name: "Оборудование", exact: true })
      .click();
    await page.getByPlaceholder("Найти ресурс").fill("Звук Kit A");
    await page.locator(".resource-card").click();
    await page.getByRole("button", { name: "Показать в календаре" }).click();
    await expect(
      page.getByLabel("Фильтр Комплект оборудования"),
    ).not.toHaveValue("");
  });
  test("Incompatible venue blocks confirmation", async ({ page }) => {
    await page.goto("/");
    await page
      .getByLabel("Постановка", { exact: true })
      .selectOption({ label: "Золотая ночь" });
    await page
      .getByLabel("Площадка", { exact: true })
      .selectOption({ label: "Камерный зал" });
    await page.getByRole("button", { name: "Проверить и назначить" }).click();
    const dialog = page.getByRole("dialog", { name: "Предварительный план" });
    await expect(
      dialog.getByText("Несовместимо", { exact: true }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Подтвердить", exact: true }),
    ).toBeDisabled();
    await expect(
      dialog.getByText("Верхняя механика отсутствует", { exact: true }),
    ).toBeVisible();
  });
  test("Rehearsal create, real drag recalculation and resize", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Репетиция", exact: true }).click();
    await page.getByLabel("Дата", { exact: true }).fill("2026-11-10");
    await page.getByLabel("Начало", { exact: true }).fill("12:00");
    await page.getByRole("button", { name: "Проверить и назначить" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(
      page.locator(".fc-event").filter({ hasText: "Северный ветер" }).first(),
    ).toBeVisible({ timeout: 60000 });
    const ev = page
      .locator(".fc-event")
      .filter({ hasText: "Северный ветер" })
      .first();
    await ev.evaluate((el) => el.scrollIntoView({ block: "center" }));
    const box = await ev.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.move(box!.x + 20, box!.y + 20);
    await page.mouse.down();
    await page.waitForTimeout(200);
    await page.mouse.move(box!.x + 20, box!.y + 80, { steps: 15 });
    await page.waitForTimeout(200);
    await page.mouse.up();
    const dialog = page.getByRole("dialog", { name: "Предварительный план" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/13:00/).first()).toBeVisible();
    let list = await (
      await request.get("/api/events?start=2026-11-10&end=2026-11-11")
    ).json();
    expect(list[0].start).toBe("2026-11-10T12:00:00");
    await dialog
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(dialog).toBeHidden();
    await expect(async () => {
      list = await (
        await request.get("/api/events?start=2026-11-10&end=2026-11-11")
      ).json();
      expect(list[0].start).toBe("2026-11-10T13:00:00");
    }).toPass();
    await page.getByRole("button", { name: "День", exact: true }).click();
    await expect(page.locator(".fc-timeGridDay-view")).toBeVisible();
    const resizer = page.locator(".fc-event-resizer-end").first();
    await page
      .locator(".fc-event")
      .first()
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.locator(".fc-event").first().hover();
    await resizer.hover();
    const rb = await resizer.boundingBox();
    await page.mouse.move(rb!.x + rb!.width / 2, rb!.y + rb!.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(200);
    await page.mouse.move(rb!.x + rb!.width / 2, rb!.y + rb!.height / 2 + 30, {
      steps: 10,
    });
    await page.mouse.up();
    await expect(dialog).toBeVisible();
    await dialog
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
  });
  test("Production drilldown, palette, AI disabled and diagnostics", async ({
    page,
  }) => {
    await page.request.post('/api/demo');
    await page.goto("/");
    await page.getByRole("button", { name: "Постановки", exact: true }).click();
    await page
      .locator(".production-card")
      .filter({ hasText: "Северный ветер" })
      .click();
    await expect(page.getByText("Артисты · составы A / B")).toBeVisible();
    await page.getByRole("button", { name: "Техника", exact: true }).click();
    await expect(
      page.getByText("Механика и световая инфраструктура"),
    ).toBeVisible();
    await page.keyboard.press("Control+k");
    await page
      .getByPlaceholder("Команда, сотрудник, постановка…")
      .fill("Белая ночь");
    await page.locator(".palette-results button").click();
    await expect(
      page.getByRole("heading", { name: "Белая ночь", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Помощник StageOS", exact: true })
      .click();
    await page
      .getByPlaceholder("Кто ведёт звук на Северном ветре?")
      .fill("Продолжительность Северный ветер");
    await page.getByRole("button", { name: "Спросить", exact: true }).click();
    const assistantBoot = await (await page.request.get('/api/bootstrap')).json();
    const duration = assistantBoot.productions.find((p:any)=>p.name === 'Северный ветер').data.duration;
    await expect(page.locator(".answer")).toContainText("Северный ветер");
    await expect(page.locator(".answer")).toContainText(String(duration));
    await page.getByRole("button", { name: "Настройки", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Диагностика" }),
    ).toBeVisible();
    await expect(
      page.getByText("Оптимальный план", { exact: true }).first(),
    ).toBeVisible();
  });
  test("Resource CRUD persists through UI", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Сотрудники", exact: true }).click();
    await page.getByRole("button", { name: "Добавить сотрудника" }).click();
    await page.getByLabel("Название / ФИО").fill("Тестовый сотрудник");
    await page.getByLabel("Подразделение",{exact:true}).fill("Звук");
    await page.getByRole("button", { name: "Сохранить ресурс" }).click();
    await page.getByPlaceholder("Найти ресурс").fill("Тестовый сотрудник");
    await page.locator(".resource-card").click();
    await page
      .getByRole("button", { name: "Редактировать", exact: true })
      .click();
    await page.getByLabel("Название / ФИО").fill("Изменённый сотрудник");
    await page.getByRole("button", { name: "Сохранить ресурс" }).click();
    await expect(
      page.getByRole("heading", { name: "Изменённый сотрудник" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Удалить", exact: true }).click();
    await page.getByPlaceholder("Найти ресурс").fill("Изменённый сотрудник");
    await expect(page.locator(".resource-card")).toHaveCount(0);
  });
  test("Database backup/import and isolated demo scenarios", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Настройки", exact: true }).click();
    await page
      .getByText("24 демонстрационных конфликта", { exact: true })
      .click();
    await page
      .getByRole("button", { name: "Превышена нагрузка", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Предварительный план" });
    await expect(dialog.getByText(/Демонстрационный сценарий:/)).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Подтвердить", exact: true }),
    ).toHaveCount(0);
    await dialog.getByRole("button", { name: "Закрыть проверку" }).click();
    const backup = await request.get("/api/database/export");
    expect(backup.status()).toBe(200);
    await page.locator("#database-upload").setInputFiles({
      name: "StageOS-backup.db",
      mimeType: "application/octet-stream",
      buffer: await backup.body(),
    });
    await expect(
      page.getByRole("heading", { name: "Поднимем занавес." }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Календарь", exact: true }).click();
    await expect(
      page.locator('.fc-event[data-start="2026-10-16T19:00:00"]'),
    ).toBeVisible({ timeout: 60000 });
  });
});
