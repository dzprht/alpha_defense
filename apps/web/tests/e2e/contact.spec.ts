import { expect, test } from "@playwright/test";

test("message and URL checks show saved guidance and present a warning after render", async ({
  page,
}, testInfo) => {
  await page.goto("/welcome");
  await page.getByRole("button", { name: "Регистрация" }).click();
  await page.getByRole("textbox", { name: "Логин" }).fill("contact_browser_user");
  await page.getByLabel("Пароль", { exact: true }).fill("synthetic-contact-password");
  await page.getByLabel("Повторите пароль").fill("synthetic-contact-password");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.getByRole("heading", { name: "Учебный аккаунт активен" })).toBeVisible();

  await page.getByRole("link", { name: "Проверка" }).click();
  await expect(page.getByText(/Сначала разрешите анализ сообщений/u)).toBeVisible();
  await expect(page.getByRole("button", { name: "Проверить", exact: true })).toBeDisabled();
  await page.getByRole("link", { name: "Аккаунт", exact: true }).click();
  await page.getByRole("checkbox", { name: /Анализировать сообщения и звонки/u }).click();
  await expect(page.getByText("Изменение сохранено.")).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /Анализировать сообщения и звонки/u }),
  ).toBeChecked();
  await page.getByRole("checkbox", { name: /Анализировать ссылки и изображения/u }).click();
  await expect(page.getByText("Изменение сохранено.")).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /Анализировать ссылки и изображения/u }),
  ).toBeChecked();

  await page.getByRole("link", { name: "Проверка" }).click();
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByText("Введите текст сообщения.")).toBeVisible();
  const text = "Срочно назовите пароль от личного кабинета";
  await page.getByLabel("Текст сообщения или расшифровки").fill(text);
  let failFirst = true;
  const keys: string[] = [];
  let submitCount = 0;
  await page.route("**/api/v1/observations", async (route) => {
    submitCount += 1;
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    if (failFirst) {
      failFirst = false;
      await route.abort();
    } else {
      await route.continue();
    }
  });
  let presentCount = 0;
  const renderedBeforePresent: boolean[] = [];
  await page.route("**/api/v1/warnings/*/present", async (route) => {
    renderedBeforePresent.push(await page.locator(".warning-panel").isVisible());
    presentCount += 1;
    await route.continue();
  });
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByText(/Не удалось связаться с сервисом/u)).toBeVisible();
  await expect(page.getByLabel("Текст сообщения или расшифровки")).toHaveValue(text);
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByText("Демонстрационный анализ", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();
  await expect(page.locator(".warning-panel")).toBeVisible();
  await page.screenshot({ fullPage: true, path: testInfo.outputPath("message-result.png") });
  const education = page.getByRole("region", { name: "Учебные материалы" });
  await expect(education.getByRole("button").first()).not.toHaveText(/_/u);
  await education.getByRole("button").first().click();
  await expect(education.locator("article h3")).toBeVisible();
  await expect.poll(() => presentCount).toBe(1);
  expect(renderedBeforePresent).toEqual([true]);
  await page.unroute("**/api/v1/warnings/*/present");
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(submitCount).toBe(2);
  const savedPath = new URL(page.url()).pathname;
  const assessmentId = savedPath.split("/").at(-1);
  if (assessmentId === undefined) {
    throw new Error("assessment ID is missing from the result URL");
  }
  await expect
    .poll(async () => {
      const response = await page.request.get(`/api/v1/assessments/${assessmentId}/warning`);
      const body = (await response.json()) as { warning: { presented_at: string | null } };
      return body.warning.presented_at;
    })
    .not.toBeNull();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();
  expect(submitCount).toBe(2);
  expect(presentCount).toBe(1);

  await page.getByRole("button", { name: "Проверить ещё раз" }).click();
  await expect(page).not.toHaveURL(new RegExp(`${assessmentId}$`, "u"));
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();
  await page.goto(savedPath);
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();

  await page.getByRole("link", { name: /Новая проверка/u }).click();
  await page.getByRole("radio", { name: "Ссылка" }).check();
  await page.getByLabel("Адрес ссылки").fill("not-a-url");
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByText("Введите полный адрес с http:// или https://.")).toBeVisible();
  const suspiciousUrl = "https://alfa-secure-check.test/card";
  await page.getByLabel("Адрес ссылки").fill(suspiciousUrl);
  let unsafeNavigation = false;
  page.on("request", (request) => {
    if (request.url().startsWith("https://alfa-secure-check.test")) {
      unsafeNavigation = true;
    }
  });
  await page.getByLabel("Адрес ссылки").press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Критический риск" })).toBeVisible();
  await expect(page.locator(".unsafe-url")).toHaveText(suspiciousUrl);
  expect(await page.locator(`a[href="${suspiciousUrl}"]`).count()).toBe(0);
  expect(unsafeNavigation).toBe(false);
  await page.setViewportSize({ width: 390, height: 800 });
  await page.screenshot({ fullPage: true, path: testInfo.outputPath("url-result-mobile.png") });
  const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(documentWidth).toBeLessThanOrEqual(390);

  await page.goto("/welcome");
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  await expect(page.getByRole("heading", { name: "Войти в учебный аккаунт" })).toBeVisible();
  await page.getByRole("button", { name: "Регистрация" }).click();
  await page.getByRole("textbox", { name: "Логин" }).fill("contact_other_user");
  await page.getByLabel("Пароль", { exact: true }).fill("synthetic-other-password");
  await page.getByLabel("Повторите пароль").fill("synthetic-other-password");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.getByRole("heading", { name: "Учебный аккаунт активен" })).toBeVisible();
  await page.goto(savedPath);
  await expect(page.getByRole("heading", { name: "Результат не открылся" })).toBeVisible();
  await expect(page.locator(".warning-panel")).toHaveCount(0);
});
