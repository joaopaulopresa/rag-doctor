import { expect, test } from "@playwright/test";
import { apiSignIn, signIn, waitForChat } from "./helpers";

// A small document whose facts are fixed here, so the test knows what the answer must cite.
const LEASE = {
  name: "northwind-office-lease.txt",
  title: "northwind office lease",
  text: [
    "NORTHWIND OFFICE LEASE",
    "",
    "1. Premises. The Landlord, Harbor Point Properties, leases Suite 410 to the Tenant, Northwind Analytics.",
    "2. Rent. The Tenant pays a monthly rent of 4,250 dollars, due on the fifth day of each month.",
    "3. Notice. Either party may end this lease by giving ninety days of written notice to the other party.",
    "4. Parking. The Tenant may use six parking spaces in the north garage at no extra cost.",
  ].join("\n"),
};

test("an uploaded document is indexed and cited by the chat, then removed", async ({ page, request }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Documents" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: LEASE.name, mimeType: "text/plain", buffer: Buffer.from(LEASE.text) });
  const row = page.getByRole("row", { name: /northwind office lease/ });
  await expect(row).toBeVisible();
  await expect(row.getByText("Indexed")).toBeVisible({ timeout: 240_000 });

  await waitForChat(request);
  await page.goto("/");
  await page.getByRole("textbox", { name: "Your question" }).fill("How much notice must be given to end the Northwind office lease?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const sources = page.getByRole("list", { name: "Passages given to the model" });
  await expect(sources.getByText(LEASE.title).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("button", { name: "Helpful", exact: true })).toBeVisible({ timeout: 90_000 });

  await apiSignIn(request);
  const removed = await request.delete("/api/admin/documents/uploads/northwind-office-lease.txt");
  expect(removed.ok()).toBeTruthy();
  await waitForChat(request);
});

test("the playground answers one question with two configurations side by side", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Playground" }).click();
  await page.getByRole("button", { name: "Ask both" }).click();
  await expect(page.getByText("Total")).toHaveCount(2, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Configuration B" })).toBeVisible();
});

test("a configuration from the history can be restored and becomes active", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Configurations" }).click();
  const restore = page.getByRole("button", { name: "Restore" }).first();
  await expect(restore).toBeVisible();
  const row = page.getByRole("row").filter({ has: restore });
  const name = (await row.locator("b").first().textContent())!.trim();
  await restore.click();
  await expect(page.locator("section").first().getByRole("heading", { name })).toBeVisible();
});
