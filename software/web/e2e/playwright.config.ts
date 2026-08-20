import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testIgnore: ["mock-cd-runtime.spec.ts", "engineering-firmware-cache-runtime.spec.ts"],
  snapshotPathTemplate: "{testDir}/__snapshots__/{testFilePath}/{arg}{ext}",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: process.env.CI
    ? [["line"], ["html", { open: "never" }]]
    : "list",
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      scale: "css",
      threshold: 0.2,
      maxDiffPixelRatio: 0.001,
    },
  },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    // Fixed to the accepted maximized desktop reference supplied after PR #29.
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
  webServer: {
    command: "npm --prefix .. run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
    // Exercise the real Vite -> Cloudflare Worker binding path. No Manager is
    // started in browser CI, so an enabled Fleet BFF must reach the Manager
    // attempt and report 503 rather than falling back to fleet_ui_disabled.
    env: {
      ...process.env,
      PLASMA_FLEET_UI_ENABLED: "1",
      PLASMA_MANAGER_API_URL: "http://127.0.0.1:18180",
    },
  },
});
