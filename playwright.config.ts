import { defineConfig, devices } from "@playwright/test";

// Runs against the Docker Compose stack: `docker compose up -d` first.
const baseURL = process.env.BASE_URL ?? "http://localhost:5310";

export default defineConfig({
  timeout: 300_000,
  expect: { timeout: 60_000 },
  workers: 1,
  reporter: [["list"]],
  use: { baseURL, viewport: { width: 1280, height: 720 }, ...devices["Desktop Chrome"] },
  projects: [
    {
      name: "e2e",
      testDir: "e2e/tests",
      outputDir: "test-results",
      use: { viewport: { width: 1280, height: 720 }, trace: "retain-on-failure" },
    },
    {
      // Scripted demos: each file records one video of the real application.
      name: "demo",
      testDir: "e2e/demo",
      testMatch: /.*\.demo\.ts/,
      outputDir: "e2e/demo/output/raw",
      timeout: 900_000,
      use: {
        viewport: { width: 1280, height: 720 },
        deviceScaleFactor: 1,
        video: { mode: "on", size: { width: 1280, height: 720 } },
      },
    },
  ],
});
