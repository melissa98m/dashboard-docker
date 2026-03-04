import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config for Docker Dashboard.
 * Prerequisite: stack must be running (make up).
 * Credentials: set E2E_USERNAME and E2E_PASSWORD, or use bootstrap admin.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  timeout: 15_000,
  expect: { timeout: 5_000 },
});
