import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLASMA_RENDER_ORIGIN ?? "https://plasma-6zz7.onrender.com";

export default defineConfig({
  testDir: "./tests",
  testMatch: "render-public-runtime.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: process.env.CI
    ? [["line"], ["html", { open: "never" }]]
    : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    viewport: { width: 1194, height: 834 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    reducedMotion: "reduce",
    locale: "zh-TW",
    timezoneId: "Asia/Taipei",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});
