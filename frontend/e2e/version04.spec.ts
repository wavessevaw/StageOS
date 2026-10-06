import { test, expect } from "@playwright/test";
test.beforeAll(async ({ request }) => {
  await request.post("/api/demo");
});
test("Selective rehearsal staff and note", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Репетиция", exact: true }).click();
  const section = page
    .locator("section")
    .filter({
      has: page.getByRole("heading", {
        name: "Кто нужен на репетиции",
        exact: true,
      }),
    });
  await section.getByRole("button", { name: "Балет", exact: true }).click();
  await section.locator(".rehearsal-person input[type=checkbox]").first().check();
  const card = section.locator('.rehearsal-person').first();
  const box = await card.boundingBox();
  const text = await card.locator('span').boundingBox();
  expect(box && text && text.x >= box.x && text.x + text.width <= box.x + box.width + 1).toBeTruthy();
  await section.getByRole("button", { name: "Звук", exact: true }).click();
  await section.locator(".rehearsal-person input[type=checkbox]").first().check();
  await page
    .getByLabel("Примечание к событию", { exact: true })
    .fill("Балет и звук. Только выбранные люди.");
  await page.getByLabel("Дата", { exact: true }).fill("2026-12-18");
  await page
    .getByRole("button", { name: "Проверить и назначить", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Предварительный план" });
  await expect(modal).toBeVisible();
  await modal.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(modal).not.toBeVisible();
  const events = await (
    await request.get("/api/events?start=2026-12-18&end=2026-12-19")
  ).json();
  const ev = events.find((e: any) => e.kind === "Репетиция");
  expect(ev).toBeTruthy();
  const detail = await (await request.get("/api/events/" + ev.id)).json();
  expect(detail.current.assignments).toHaveLength(2);
  expect(detail.current.notes).toContain("Балет и звук");
});
test("Create venue with mechanical resources through UI", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Площадки", exact: true }).click();
  await page
    .getByRole("button", { name: "Добавить площадку", exact: true })
    .click();
  await page
    .getByLabel("Название площадки", { exact: true })
    .fill("Новая тестовая сцена");
  await page.getByLabel("Мест в зрительном зале", { exact: true }).fill("450");
  await page.getByLabel("Количество штанкетов", { exact: true }).fill("12");
  await page
    .getByRole("button", { name: "Сохранить площадку", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Новая тестовая сцена", exact: true }),
  ).toBeVisible();
  expect(await page.locator("body").innerText()).not.toMatch(
    /Fly Bar|venue_id|capacity|available/,
  );
  const b = await (await request.get("/api/bootstrap")).json();
  const v = b.resources.find((r: any) => r.name === "Новая тестовая сцена");
  expect(v.data.seats).toBe(450);
  expect(
    b.resources.filter(
      (r: any) => r.kind === "Fly Bar" && r.data.venue_id === v.id,
    ),
  ).toHaveLength(12);
});
test("Create four physical units inside production passport", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Постановки", exact: true }).click();
  await page.locator(".production-card").first().click();
  await page.getByRole("button", { name: "Редактировать постановку" }).click();
  await page.getByRole("button", { name: "Техника", exact: true }).click();
  const box = page
    .locator("section")
    .filter({
      has: page.getByRole("heading", {
        name: "Поштучное имущество постановки",
      }),
    })
    .last();
  await box.getByLabel("Название позиции", { exact: true }).fill("BSW 350");
  await box.getByLabel("Количество, шт.", { exact: true }).fill("4");
  await box
    .getByRole("button", { name: "Создать и добавить", exact: true })
    .click();
  await expect(box.getByText("BSW 350 — 4 шт.", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Сохранить постановку", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "Сохранить постановку", exact: true })).not.toBeVisible();
  const b = await (await request.get("/api/bootstrap")).json();
  const ids = b.productions[0].data.items;
  expect(ids).toHaveLength(4);
  expect(b.resources.filter((r: any) => ids.includes(r.id))).toHaveLength(4);
});
test("Force incompatible performance keeps conflicts and audit reason", async ({
  page,
  request,
}) => {
  const b = await (await request.get("/api/bootstrap")).json();
  await page.goto("/");
  await page.getByLabel("Дата", { exact: true }).fill("2026-12-20");
  await page
    .getByLabel("Постановка", { exact: true })
    .selectOption(
      String(b.productions.find((p: any) => p.name === "Золотая ночь").id),
    );
  await page
    .getByLabel("Площадка", { exact: true })
    .selectOption(
      String(b.resources.find((r: any) => r.name === "Камерный зал").id),
    );
  await page
    .getByRole("button", { name: "Проверить и назначить", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Предварительный план" });
  await modal
    .getByLabel("Назначить принудительно с сохранением конфликтов")
    .check();
  await modal
    .getByPlaceholder("Обязательная причина, не менее 12 символов")
    .fill("Учебное принудительное назначение с известными ограничениями");
  await modal.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(modal).not.toBeVisible();
  const events = await (
    await request.get("/api/events?start=2026-12-20&end=2026-12-21")
  ).json();
  expect(events[0].health).toBe("CONFLICT");
  expect(events[0].data.request.force).toBe(true);
});
