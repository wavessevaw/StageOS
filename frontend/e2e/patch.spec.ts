import { test, expect } from "@playwright/test";
test.beforeAll(async ({ request }) => {
  await request.post("/api/demo");
});
test("Editable production timing and replacement persisted from event", async ({
  page,
  request,
}) => {
  const b = await (await request.get("/api/bootstrap")).json();
  const req = {
    production_id: b.productions[0].id,
    venue_id: b.resources.find((r: any) => r.name === "Большой зал").id,
    start: "2026-11-16T19:00:00",
    cast: "B",
  };
  const plan = await (await request.post("/api/preview", { data: req })).json();
  const ev = await (
    await request.post("/api/events", {
      data: { request: req, fingerprint: plan.fingerprint },
    })
  ).json();
  await page.goto("/");
  await page.getByRole("button", { name: "Календарь", exact: true }).click();
  // Open through calendar after navigating to November.
  await page.getByRole("button", { name: "Месяц", exact: true }).click();
  const next = page.locator(".fc-next-button");
  if (await next.count()) await next.click();
  else {
    await page.getByRole("button", { name: "→", exact: true }).click();
  }
  await page.locator('.fc-event[data-start="2026-11-16T19:00:00"]').click();
  const detail = page.getByRole("dialog", { name: "Карточка события" });
  await detail.getByRole("button", { name: "Изменить", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Предварительный план" });
  await expect(modal).toBeVisible();
  const departure = modal.getByLabel("Начало Выезд", { exact: true });
  await departure.fill("2026-11-16T08:00");
  await modal
    .getByRole("heading", { name: "Производственный план", exact: true })
    .click();
  await expect(modal.getByLabel("Начало Выезд", { exact: true })).toHaveValue(
    "2026-11-16T08:00",
  );
  await expect(
    modal.getByRole("button", { name: "Снять закрепление" }),
  ).toBeVisible();
  await modal.locator("summary").filter({ hasText: "Артисты" }).first().click();
  const replace = modal
    .locator('select[aria-label^="Заменить"]')
    .filter({ visible: true })
    .first();
  const before = await replace.inputValue();
  const options = await replace
    .locator("option")
    .evaluateAll((nodes) => nodes.map((n) => (n as HTMLOptionElement).value));
  const chosen = options.find((x) => x !== before)!;
  await replace.selectOption(chosen);
  await expect(
    modal.getByRole("button", { name: "Подтвердить", exact: true }),
  ).toBeEnabled();
  await modal.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(modal).not.toBeVisible();
  const updated = await (await request.get("/api/events/" + ev.id)).json();
  expect(updated.current.request.task_overrides["Выезд"].start).toBe(
    "2026-11-16T08:00:00",
  );
  expect(Object.values(updated.current.request.replacements)).toContain(
    +chosen,
  );
});
test("People categories and statistics, equipment categories, passport editor", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Сотрудники", exact: true }).click();
  await page.getByRole("button", { name: "Оркестр", exact: true }).click();
  await expect(page.locator(".resource-card")).toHaveCount(35);
  await page.locator(".resource-card").first().click();
  await expect(
    page.getByRole("heading", {
      name: "Статистика сотрудника · всё расписание",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Оборудование", exact: true }).click();
  await page.getByRole("button", { name: "Свет", exact: true }).click();
  await page.getByRole("button", { name: "BSW", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Светодиодная линейка", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Постановки", exact: true }).click();
  await page.locator(".production-card").first().click();
  await page.getByRole("button", { name: "Редактировать постановку" }).click();
  await page
    .getByLabel("Название постановки", { exact: true })
    .fill("Северный ветер — редакция");
  await page.getByRole("button", { name: "Сохранить постановку" }).click();
  await expect(
    page
      .getByRole("heading", { name: "Северный ветер — редакция", exact: true })
      .first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Добавить спектакль", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Добавить спектакль", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Люди", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Роли и составы" }),
  ).toBeVisible();
});
test("Proposal rejection in notifications", async ({ page, request }) => {
  const b = await (await request.get("/api/bootstrap")).json();
  const response = await request.post("/api/proposals", {
    data: {
      production_id: b.productions[0].id,
      venue_id: b.resources.find((r: any) => r.name === "Большой зал").id,
      start: "2026-11-20T19:00:00",
      cast: "B",
    },
  });
  expect(response.ok()).toBeTruthy();
  await page.goto("/");
  await page
    .getByRole("button", { name: "Уведомления", exact: true })
    .first()
    .click();
  await page
    .locator("summary")
    .filter({ hasText: "Предложение" })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Отклонить", exact: true })
    .first()
    .click();
  await expect(
    page.getByText("Отклонено", { exact: true }).first(),
  ).toBeVisible();
});

test("Create a new production through category editor", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Добавить спектакль", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Название постановки", { exact: true })
    .fill("Новая постановка из интерфейса");
  await page.getByRole("button", { name: "Люди", exact: true }).click();
  const singles = page.locator(".passport-fields select:not([multiple])");
  for (let i = 0; i < (await singles.count()); i++) {
    const select = singles.nth(i);
    const options = await select
      .locator("option")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLOptionElement).value));
    const id = options.find((x) => x !== "0");
    if (id) await select.selectOption(id);
  }
  await page
    .getByRole("button", { name: "Сохранить постановку", exact: true })
    .click();
  await expect(
    page
      .getByRole("heading", {
        name: "Новая постановка из интерфейса",
        exact: true,
      })
      .first(),
  ).toBeVisible();
  const b = await (await request.get("/api/bootstrap")).json();
  expect(
    b.productions.some((p: any) => p.name === "Новая постановка из интерфейса"),
  ).toBeTruthy();
});
