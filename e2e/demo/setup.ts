import { expect, type APIRequestContext, type BrowserContext } from "@playwright/test";

export const ADMIN = { email: process.env.ADMIN_EMAIL ?? "admin@ragdoctor.demo", password: process.env.ADMIN_PASSWORD ?? "doctor-admin" };

/** Sign in through the API and return the session cookies for a recording context. */
export async function adminCookies(context: BrowserContext) {
  const response = await context.request.post("/api/auth/login", { data: ADMIN });
  expect(response.ok()).toBeTruthy();
  return context.cookies();
}

export async function waitReady(request: APIRequestContext) {
  await expect
    .poll(async () => (await (await request.get("/api/status")).json()).ready, { timeout: 300_000, intervals: [2000] })
    .toBe(true);
}

export async function waitJob(request: APIRequestContext, id: number) {
  await expect
    .poll(async () => (await (await request.get(`/api/admin/jobs/${id}`)).json()).job.status, { timeout: 600_000, intervals: [2000] })
    .toMatch(/done|failed/);
}
