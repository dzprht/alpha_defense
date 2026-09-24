import { expect, test } from "@playwright/test";

test("two independent contexts share one account but isolate another", async ({ browser }) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  const other = await browser.newContext();
  const firstPage = await first.newPage();
  const secondPage = await second.newPage();
  const otherPage = await other.newPage();

  try {
    await firstPage.goto("/welcome");
    await firstPage.getByRole("button", { name: "Регистрация" }).click();
    await firstPage.getByRole("textbox", { name: "Логин" }).fill("browser_user_one");
    await firstPage.getByLabel("Пароль", { exact: true }).fill("synthetic-password-one");
    await firstPage.getByLabel("Повторите пароль").fill("synthetic-password-one");
    await firstPage.getByRole("button", { name: "Создать аккаунт" }).click();
    await expect(firstPage.getByRole("heading", { name: "Учебный аккаунт активен" })).toBeVisible();
    await firstPage.getByRole("checkbox", { name: /Участвовать в исследовании/u }).click();
    await expect(firstPage.getByText("Изменение сохранено.")).toBeVisible();
    await expect(
      firstPage.getByRole("checkbox", { name: /Участвовать в исследовании/u }),
    ).toBeChecked();

    await secondPage.goto("/welcome");
    await secondPage.getByRole("textbox", { name: "Логин" }).fill("browser_user_one");
    await secondPage.getByLabel("Пароль", { exact: true }).fill("synthetic-password-bad");
    await secondPage.getByRole("button", { name: "Войти в аккаунт" }).click();
    await expect(secondPage.getByRole("alert")).toBeVisible();
    await expect(secondPage.getByRole("textbox", { name: "Логин" })).toHaveValue(
      "browser_user_one",
    );
    await expect(
      secondPage.getByRole("heading", { name: "Войти в учебный аккаунт" }),
    ).toBeVisible();
    await secondPage.getByLabel("Пароль", { exact: true }).fill("synthetic-password-one");
    await secondPage.getByRole("button", { name: "Войти в аккаунт" }).click();
    await expect(
      secondPage.getByRole("heading", { name: "Учебный аккаунт активен" }),
    ).toBeVisible();
    await expect(
      secondPage.getByRole("checkbox", { name: /Участвовать в исследовании/u }),
    ).toBeChecked();
    await secondPage.reload();
    await expect(
      secondPage.getByRole("checkbox", { name: /Участвовать в исследовании/u }),
    ).toBeChecked();

    await otherPage.goto("/welcome");
    await otherPage.getByRole("button", { name: "Регистрация" }).click();
    await otherPage.getByRole("textbox", { name: "Логин" }).fill("browser_user_two");
    await otherPage.getByLabel("Пароль", { exact: true }).fill("synthetic-password-two");
    await otherPage.getByLabel("Повторите пароль").fill("synthetic-password-two");
    await otherPage.getByRole("button", { name: "Создать аккаунт" }).click();
    await expect(otherPage.getByRole("heading", { name: "Учебный аккаунт активен" })).toBeVisible();
    await expect(
      otherPage.getByRole("checkbox", { name: /Участвовать в исследовании/u }),
    ).not.toBeChecked();

    await firstPage.getByRole("button", { name: "Выйти из аккаунта" }).click();
    await expect(firstPage.getByRole("heading", { name: "Войти в учебный аккаунт" })).toBeVisible();
    await secondPage.reload();
    await expect(
      secondPage.getByRole("heading", { name: "Учебный аккаунт активен" }),
    ).toBeVisible();
  } finally {
    await Promise.all([first.close(), second.close(), other.close()]);
  }
});
