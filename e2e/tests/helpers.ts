import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const ADMIN = { email: process.env.ADMIN_EMAIL ?? "admin@ragdoctor.demo", password: process.env.ADMIN_PASSWORD ?? "doctor-admin" };

export async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin\//);
}

export async function apiSignIn(request: APIRequestContext) {
  const response = await request.post("/api/auth/login", { data: ADMIN });
  expect(response.ok()).toBeTruthy();
}

export async function waitForChat(request: APIRequestContext) {
  await expect
    .poll(async () => (await (await request.get("/api/status")).json()).ready, { timeout: 240_000, intervals: [2000] })
    .toBe(true);
}
