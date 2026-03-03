import { test, expect } from "@playwright/test";

/**
 * Containers page E2E.
 * Requires authenticated session (E2E_USERNAME + E2E_PASSWORD).
 * Uses storageState to reuse login across tests.
 */
const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";
const hasCreds = Boolean(username && password);

test.describe("Containers page", () => {
  test.use({
    storageState: { cookies: [], origins: [] },
  });

  test.beforeEach(async ({ page }) => {
    test.skip(!hasCreds, "requires E2E_USERNAME and E2E_PASSWORD");
    await page.goto("/");
    const loginBtn = page.getByRole("button", { name: "Se connecter" }).first();
    if (await loginBtn.isVisible()) {
      await loginBtn.click();
      await page.getByPlaceholder("admin").fill(username);
      await page.getByPlaceholder("Saisir le mot de passe").fill(password);
      await page.getByRole("button", { name: "Connexion" }).click();
      await expect(page.getByRole("heading", { name: /Conteneurs Docker/i })).toBeVisible({
        timeout: 10_000,
      });
    }
  });

  test("displays containers list or empty state", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /Conteneurs Docker/i })
    ).toBeVisible();
    const content = await page.textContent("main");
    expect(content).toBeDefined();
    expect(content?.length).toBeGreaterThan(0);
  });
});
