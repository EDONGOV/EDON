import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8080",
    trace: "on-first-retry",
    // Pass a demo token so auth gate is bypassed in tests
    storageState: undefined,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // To run E2E in CI with a live server, use start-server-and-test:
  //   npx start-server-and-test 'npm run dev' http://localhost:8080 'npm run e2e'
  // Or set webServer here for automatic start:
  // webServer: {
  //   command: "npm run dev",
  //   url: "http://localhost:8080",
  //   reuseExistingServer: !process.env.CI,
  // },
});
