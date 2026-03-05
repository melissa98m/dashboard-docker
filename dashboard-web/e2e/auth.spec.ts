import { test, expect } from "@playwright/test";

/**
 * Auth flow E2E.
 * Requires E2E_USERNAME and E2E_PASSWORD (e.g. bootstrap admin credentials).
 * Skip if not set: npx playwright test --grep-invert "@skip-if-no-creds"
 */
const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";
const hasCreds = Boolean(username && password);

async function ensureLoginPanelOpen(page: import("@playwright/test").Page) {
  const toggle = page.locator(".auth-panel .theme-toggle");
  const usernameInput = page.getByPlaceholder("admin");
  const logoutBtn = page.getByRole("button", {
    name: "Déconnexion",
    exact: true,
  });
  const backdrop = page.locator("button.auth-panel-backdrop");

  // App can auto-open auth panel after an auth error event right after navigation.
  await page.waitForTimeout(300);
  if (await usernameInput.isVisible()) {
    return;
  }

  if (await backdrop.isVisible()) {
    // If panel is already opening, give it a brief chance before toggling.
    await page.waitForTimeout(300);
    if (await usernameInput.isVisible()) {
      return;
    }
    await backdrop.click({ force: true });
    await expect(backdrop).toBeHidden({ timeout: 5000 });
  }

  await toggle.click({ force: true });
  await expect(usernameInput).toBeVisible({ timeout: 5000 });

  if (await logoutBtn.isVisible()) {
    await logoutBtn.click();
    await expect(backdrop).toBeHidden({ timeout: 5000 });
    await toggle.click({ force: true });
    await expect(usernameInput).toBeVisible({ timeout: 5000 });
  }
}

test.describe("Auth flow", () => {
  test("shows login prompt when unauthenticated", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Pour accéder au dashboard, veuillez vous connecter.")
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Se connecter" }).first()
    ).toBeVisible();
  });

  test("can open auth panel and see login form", async ({ page }) => {
    await page.goto("/");
    await ensureLoginPanelOpen(page);
    await expect(page.getByPlaceholder("admin")).toBeVisible({ timeout: 3000 });
    await expect(page.getByPlaceholder("Saisir le mot de passe")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Connexion", exact: true })
    ).toBeVisible();
  });

  test("login and access containers page", async ({ page }) => {
    test.skip(!hasCreds, "requires E2E_USERNAME and E2E_PASSWORD");
    await page.goto("/");
    await ensureLoginPanelOpen(page);

    await page.getByPlaceholder("admin").fill(username);
    await page.getByPlaceholder("Saisir le mot de passe").fill(password);
    await page.getByRole("button", { name: "Connexion", exact: true }).click();

    await expect(
      page.getByRole("heading", { name: /Conteneurs Docker/i })
    ).toBeVisible({
      timeout: 10_000,
    });
  });
});
