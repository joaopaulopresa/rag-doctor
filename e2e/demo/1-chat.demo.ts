import { expect, test } from "@playwright/test";
import { Director } from "./director";
import { waitReady } from "./setup";

const QUESTIONS = [
  "Consider the Promotion Agreement between Depomed, Inc. and King Pharmaceuticals, Inc. for Glumetza; Is there a cap on liability under this contract?",
  "Consider VELCO's Non-Disclosure Agreement; Does the document allow the Receiving Party to share some Confidential Information with their employees?",
];

test("chat: three questions, each citation opens its source passage", async ({ browser, baseURL, request }) => {
  await waitReady(request);
  const d = await Director.start(browser, baseURL!, "chat");
  const { page } = d;
  await page.goto("/");
  d.mark("hero_start");
  await expect(page.getByRole("heading", { name: "Ask the document library" })).toBeVisible();
  await d.caption("Ask questions about 54 contracts, NDAs and privacy policies.", 2400);
  await d.screenshot("chat-start.png");

  const answered = (n: number) => expect(page.getByRole("button", { name: "Helpful", exact: true })).toHaveCount(n, { timeout: 120_000 });
  const lastTurn = () => page.locator("article.turn").last();

  // 1. A suggested question. From the page load to here is the README's hero animation.
  await d.click(page.getByRole("button", { name: /Viber Messenger/ }));
  await answered(1);
  await d.caption("The answer cites the passages it used.", 2200);
  await d.click(lastTurn().locator("button.cite").first());
  await d.caption("A citation opens the passage, highlighted in its document.", 2800);
  await d.pause(1500);
  d.mark("hero_end");
  await d.screenshot("chat-citation.png");
  await d.hideCaption();

  // 2 and 3. Typed questions.
  for (const [index, question] of QUESTIONS.entries()) {
    await d.type(page.getByRole("textbox", { name: "Your question" }), question);
    await page.keyboard.press("Enter");
    await answered(index + 2);
    await d.pause(900);
    await d.click(lastTurn().locator("button.cite").first());
    await d.pause(2200);
  }
  await d.caption("Answers come from the configuration the lab and the doctor tuned.", 2800);
  await d.finish();
});
