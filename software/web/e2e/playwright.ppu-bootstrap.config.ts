import { defineConfig, devices } from "@playwright/test";

const artifactRoot = "../../../artifacts/ppu-bootstrap-browser";

export default defineConfig({
  testDir: "./tests",
  testMatch: ["ppu-runtime-deployment-real-stack.spec.ts"],
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
  expect: { timeout: 20_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.PPU_BOOTSTRAP_WEB_URL ?? "http://127.0.0.1:15174",
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
