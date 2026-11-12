import { expect, test } from "@playwright/test";
import { waitForChat } from "./helpers";

test("an anonymous visitor gets an answer with citations that open the source passage", async ({ page, request }) => {
  await waitForChat(request);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Ask the document library" })).toBeVisible();
  await page.getByRole("button", { name: /Viber Messenger/ }).click();

  // Passages arrive first, then the answer with checked citations.
  await expect(page.getByRole("list", { name: "Passages given to the model" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Helpful", exact: true })).toBeVisible({ timeout: 90_000 });

  await page.getByRole("list", { name: "Passages given to the model" }).getByRole("button").first().click();
  const panel = page.getByRole("complementary", { name: "Source document" });
  await expect(panel).toBeVisible();
  await expect(panel.locator("mark")).not.toBeEmpty();
});

test("a thumbs-down sends the question to the review queue", async ({ page, request }) => {
  await waitForChat(request);
  await page.goto("/");
  await page.getByRole("button", { name: /VELCO/ }).click();
  await page.getByRole("button", { name: "Not helpful" }).click({ timeout: 90_000 });
  await expect(page.getByText("The question was sent to the review queue.")).toBeVisible();
});
