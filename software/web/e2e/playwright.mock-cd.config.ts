import { defineConfig, devices } from "@playwright/test";

const artifactRoot = "../../../artifacts/mock-cd-browser";

export default defineConfig({
  testDir: "./tests",
  testMatch: ["mock-cd-runtime.spec.ts", "engineering-programming-image-cache-runtime.spec.ts"],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  timeout: 120_000,
  reporter: [
    ["line"],
    ["html", { open: "never", outputFolder: `${artifactRoot}/playwright-report` }],
    ["json", { outputFile: `${artifactRoot}/playwright-results.json` }],
  ],
  outputDir: `${artifactRoot}/test-results`,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.MOCK_CD_WEB_URL ?? "http://127.0.0.1:15173",
    viewport: { width: 1680, height: 900 },
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
