import { test, expect } from "@playwright/test";

const DEMO_URL = "http://localhost:8080/#token=demo";

test.describe("Dashboard page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(DEMO_URL);
    await page.waitForLoadState("networkidle");
  });

  test("page renders without JS errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(DEMO_URL);
    await page.waitForLoadState("networkidle");
    expect(errors).toHaveLength(0);
  });

  test("top navigation is present", async ({ page }) => {
    // TopNav should be rendered
    const nav = page.locator("nav, header, [role=navigation]").first();
    await expect(nav).toBeVisible({ timeout: 5000 });
  });

  test("page has content — not blank", async ({ page }) => {
    await page.waitForTimeout(500); // allow React to hydrate
    const bodyText = await page.evaluate(() => document.body.innerText.trim());
    expect(bodyText.length).toBeGreaterThan(10);
  });
});
