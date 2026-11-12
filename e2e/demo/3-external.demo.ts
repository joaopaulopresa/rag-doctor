import { expect, test } from "@playwright/test";
import { Director } from "./director";
import { adminCookies } from "./setup";

test("external: connect a weak RAG service and diagnose it", async ({ browser, baseURL }) => {
  const setup = await browser.newContext({ baseURL });
  const cookies = await adminCookies(setup);
  await setup.close();

  const d = await Director.start(browser, baseURL!, "external", cookies);
  const { page } = d;
  await page.goto("/admin/external");
  await expect(page.getByRole("heading", { name: "Connect a system" })).toBeVisible();
  await d.caption("Point the doctor at another RAG system: here a deliberately weak support bot.", 3000);
  await d.glide(page.getByLabel("Answer in the reply"));
  await d.caption("Say where the question goes and where the answer and the passages come back.", 3000);
  await d.click(page.getByRole("button", { name: "Test the connection" }));
  await expect(page.getByText(/passages read from the reply/)).toBeVisible({ timeout: 120_000 });
  await d.pause(1800);
  await d.click(page.getByRole("button", { name: "Save" }));
  const examine = page.getByRole("button", { name: /^Examine \d+ questions/ });
  await expect(examine).toBeVisible();
  await d.click(examine);

  await expect(page.getByRole("heading", { name: "Prescription" })).toBeVisible({ timeout: 600_000 });
  const correct = (await page.locator(".big-number").first().textContent())?.trim();
  await d.glide(page.locator(".strip-bar"));
  await d.caption(`${correct} correct, judged on the same questions and with the same judge as this app.`, 3200);
  await d.screenshot("external-findings.png");
  const item = page.locator("li.rx").first();
  await d.scrollTo(item);
  await d.glide(item);
  await d.caption("It returns no candidates, so the doctor says what it cannot tell apart.", 3400);
  await d.scrollTo(page.locator(".findings"));
  await d.click(page.getByRole("button", { name: /^Not retrieved/ }));
  await d.scrollTo(page.getByRole("heading", { name: /^Cases/ }));
  await d.click(page.locator("table").last().getByRole("link").first());
  await expect(page.getByRole("list", { name: "Where the answer went wrong" })).toBeVisible();
  await d.glide(page.locator(".trace-stage").nth(1));
  await d.caption("The gold passage was not among the two passages it gave its model.", 3200);
  await d.screenshot("external-case.png");
  await d.finish();
});
