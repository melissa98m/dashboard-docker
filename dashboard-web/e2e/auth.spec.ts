import { test, expect } from "@playwright/test";

/**
 * Auth flow E2E.
 * Requires E2E_USERNAME and E2E_PASSWORD (e.g. bootstrap admin credentials).
 * Skip if not set: npx playwright test --grep-invert "@skip-if-no-creds"
 */
const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";
const hasCreds = Boolean(username && password);

test.describe("Auth flow", () => {
  test("shows login prompt when unauthenticated", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Pour accéder au dashboard, veuillez vous connecter.")
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Se connecter" }).first()).toBeVisible();
  });

  test("can open auth panel and see login form", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Se connecter" }).first().click();
    await expect(page.getByPlaceholder("admin")).toBeVisible({ timeout: 3000 });
    await expect(page.getByPlaceholder("Saisir le mot de passe")).toBeVisible();
    await expect(page.getByRole("button", { name: "Connexion" })).toBeVisible();
  });

  test("login and access containers page", async ({ page }) => {
    test.skip(!hasCreds, "requires E2E_USERNAME and E2E_PASSWORD");
    await page.goto("/");
    await page.getByRole("button", { name: "Se connecter" }).first().click();

    await page.getByPlaceholder("admin").fill(username);
    await page.getByPlaceholder("Saisir le mot de passe").fill(password);
    await page.getByRole("button", { name: "Connexion" }).click();

    await expect(page.getByRole("heading", { name: /Conteneurs Docker/i })).toBeVisible({
      timeout: 10_000,
    });
  });
});
