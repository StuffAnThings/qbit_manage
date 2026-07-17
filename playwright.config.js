import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/web-ui",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    browserName: "chromium",
    headless: true,
  },
});
