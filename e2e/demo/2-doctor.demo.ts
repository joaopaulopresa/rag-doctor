import { expect, test } from "@playwright/test";
import { Director } from "./director";
import { adminCookies, waitJob, waitReady } from "./setup";

/** A typical first build: the starting point the doctor examines. */
const FIRST_BUILD = {
  selection: { chunker: "recursive", embedder: "bge-m3", search_mode: "hybrid", reranker: null, generator: "granite-4.2-8b", top_k: 5, candidates: 20 },
  name: "First build",
  note: "First build: recursive chunks, bge-m3, hybrid search",
};

test("doctor: examine, open a case, run the prescribed experiment, apply, before/after", async ({ browser, baseURL }) => {
  // Setup, not recorded: sign in and put the chat on the first build.
  const setup = await browser.newContext({ baseURL });
  const cookies = await adminCookies(setup);
  const applied = await (await setup.request.post("/api/admin/configurations/apply", { data: FIRST_BUILD })).json();
  if (applied.job) await waitJob(setup.request, applied.job.id);
  await waitReady(setup.request);
  await setup.close();

  const d = await Director.start(browser, baseURL!, "doctor", cookies);
  const { page } = d;

  await page.goto("/admin/configurations");
  await expect(page.getByText(/Active since/)).toBeVisible();
  await d.caption("The chat runs on a first build: recursive chunks, bge-m3 embeddings, hybrid search, no reranker.", 3600);

  await d.click(page.getByRole("link", { name: "Examinations" }));
  await d.caption("Examine it on 60 questions from the gold question set.", 2200);
  await d.click(page.getByRole("button", { name: "Start the examination" }));
  await expect(page.getByRole("heading", { name: "Prescription" })).toBeVisible({ timeout: 600_000 });
  await d.pause(600);
  const correct = (await page.locator(".big-number").first().textContent())?.trim();
  await d.glide(page.locator(".strip-bar"));
  await d.caption(`${correct} correct. Each wrong answer is traced to the stage where it went wrong.`, 3400);
  await d.screenshot("doctor-findings.png");

  // One "not retrieved" case.
  await d.click(page.getByRole("button", { name: /^Not retrieved/ }));
  await d.scrollTo(page.getByRole("heading", { name: /^Cases/ }));
  await d.click(page.locator("table").last().getByRole("link").first());
  await expect(page.getByRole("list", { name: "Where the answer went wrong" })).toBeVisible();
  await d.glide(page.locator(".trace-stage").first());
  await d.caption("Not retrieved: the gold passage is not among the 20 candidates the search returned.", 3400);
  await d.screenshot("doctor-case.png");
  await d.click(page.getByRole("button", { name: "Open in the document" }));
  await d.caption("The gold evidence, in its document.", 2200);
  await d.click(page.getByRole("button", { name: "Close the document" }));

  // The prescribed experiment.
  await d.click(page.locator(".page-head a").nth(1));
  await expect(page.getByRole("heading", { name: "Prescription" })).toBeVisible();
  const item = page.locator("li.rx").filter({ hasText: "Not retrieved" });
  await d.scrollTo(item);
  await d.caption("The prescription comes from measurement: an experiment varies only the failing stage.", 3000);
  await d.click(item.getByRole("button", { name: "Run this experiment" }));
  await expect(item.getByRole("button", { name: "Apply to the chat" })).toBeVisible({ timeout: 600_000 });
  await d.scrollTo(item.locator("table"), 120);
  await d.glide(item.locator("tr.chosen"));
  await d.caption("Measured on the same 60 questions, with the gain over the current configuration.", 3600);
  await d.screenshot("doctor-experiment.png");
  await d.click(item.getByRole("button", { name: "Apply to the chat" }));
  await d.caption("The winner is now the chat's configuration; the old one stays in the history.", 2600);

  // Re-examine and compare.
  await d.scrollTo(page.getByRole("heading", { name: "Prescription" }));
  await d.click(page.getByRole("button", { name: "Re-examine the active configuration on these questions" }));
  await expect(page.getByRole("link", { name: /Compare with/ })).toBeVisible({ timeout: 600_000 });
  await d.click(page.getByRole("link", { name: /Compare with/ }));
  await expect(page.getByRole("heading", { name: "Before and after" })).toBeVisible();
  const before = (await page.locator(".ba-side .big-number").first().textContent())?.trim();
  const after = (await page.locator(".ba-side .big-number").last().textContent())?.trim();
  const significant = (await page.locator(".ba-diff .faint").textContent())?.trim();
  await d.glide(page.locator(".ba-diff"));
  await d.caption(`Before and after on the same questions: ${before} to ${after} correct, ${significant}.`, 3800);
  await d.screenshot("doctor-before-after.png");
  await d.click(page.getByRole("tab", { name: /Fixed/ }));
  await d.pause(1800);
  await d.finish();
});
