import { test, expect } from "@playwright/test";

const DECISIONS_URL = "http://localhost:8080/decisions#token=demo";
const DEMO_URL = "http://localhost:8080/#token=demo";

test.describe("Decisions page", () => {
  test("decisions page loads", async ({ page }) => {
    await page.goto(DEMO_URL);
    await page.waitForLoadState("networkidle");
    // Navigate to decisions
    const decisionsLink = page.locator("a[href*='decisions'], [data-testid='decisions-link']").first();
    if (await decisionsLink.count() > 0) {
      await decisionsLink.click();
      await page.waitForLoadState("networkidle");
    } else {
      await page.goto(DECISIONS_URL);
      await page.waitForLoadState("networkidle");
    }
    const bodyText = await page.evaluate(() => document.body.innerText.trim());
    expect(bodyText.length).toBeGreaterThan(10);
  });

  test("decisions page does not crash", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(DECISIONS_URL);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    expect(errors).toHaveLength(0);
  });
});
