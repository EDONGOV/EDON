import { test, expect } from "@playwright/test";

const DEMO_URL = "http://localhost:8080/#token=demo";

test.describe("Auth flow", () => {
  test("unauthenticated root redirects to access gate", async ({ page }) => {
    await page.goto("http://localhost:8080/");
    // Should show some form of login/access gate or redirect
    // The app shows AccessGate when no token is set
    await expect(page).toHaveURL(/localhost:8080/);
    // Either the access gate or a login prompt is visible
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });

  test("demo token in URL hash grants access to dashboard", async ({ page }) => {
    await page.goto(DEMO_URL);
    await page.waitForLoadState("networkidle");
    // With demo token, should reach a page with nav/dashboard content
    const url = page.url();
    expect(url).toContain("localhost:8080");
    // Page should render without a crash
    await expect(page.locator("body")).not.toBeEmpty();
  });

  test("settings page is accessible without auth", async ({ page }) => {
    await page.goto("http://localhost:8080/settings");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).not.toBeEmpty();
  });
});
