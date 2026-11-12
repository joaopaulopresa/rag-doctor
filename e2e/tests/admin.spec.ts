import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("the admin area asks for a sign-in and rejects a wrong password", async ({ page }) => {
  await page.goto("/admin/doctor");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("E-mail").fill("admin@ragdoctor.demo");
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Wrong e-mail or password.")).toBeVisible();
});

test("the lab lists the library and the active configuration", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Documents" }).click();
  await expect(page.getByText(/54 documents/)).toBeVisible();
  await page.getByRole("link", { name: "Question set" }).click();
  await page.getByRole("tab", { name: /Accepted/ }).click();
  await expect(page.getByRole("tab", { name: /Accepted/ })).toContainText(/\d+/);
  await page.getByRole("link", { name: "Configurations" }).click();
  await expect(page.getByText(/Active since/)).toBeVisible();
});

test("the doctor examines the active configuration and explains a case", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("Questions").fill("6");
  await page.getByRole("button", { name: "Start the examination" }).click();
  await expect(page.getByRole("heading", { name: "Prescription" })).toBeVisible({ timeout: 240_000 });
  await expect(page.getByRole("img", { name: /Correct/ })).toBeVisible();
  await page.locator("table").last().getByRole("link").first().click();
  await expect(page.getByRole("list", { name: "Where the answer went wrong" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Gold evidence" })).toBeVisible();
});

test("an external system can be connected and tested", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "External systems" }).click();
  await page.getByRole("button", { name: "Test the connection" }).click();
  await expect(page.getByText(/passages read from the reply/)).toBeVisible({ timeout: 90_000 });
});
