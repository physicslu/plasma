import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = "mock-facility-01-ppu-01";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      }],
    }],
  };
}

function status() {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
      site_count: 2,
      enabled_site_count: 2,
      capabilities: { max_supported_sites: 2, operations: ["erase", "program", "verify", "read"] },
    },
    sites: [1, 2].map(siteId => ({
      site_id: siteId,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

async function installProductionCatalog(page: Page) {
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "production-log-parity-session-000000",
            previous_session_cleared: false,
            programming_asset_cache_scope: "connection-session-and-ppu",
          },
        }),
      });
      return;
    }

    if (path === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

test("Production log uses the Engineering log panel contract", async ({ page }) => {
  await installProductionCatalog(page);
  await page.goto("/fleet");

  const log = page.getByLabel("Production batch log");
  await expect(log).toBeVisible();
  await expect(page.getByRole("button", { name: "Download .log", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Production log filters")).toBeVisible();
  for (const category of ["USR", "NET", "PPU", "DAT", "BAT", "SYS"]) {
    await expect(page.getByLabel(`Production log filter ${category}`)).toBeChecked();
  }

  await expect(log).toContainText("[NET] [PROVIDER] MOCK");
  const logHeight = await log.evaluate(element => Number.parseFloat(getComputedStyle(element).height));
  expect(logHeight).toBeGreaterThanOrEqual(260);

  await page.getByLabel("Production log filter NET").uncheck();
  await expect(log).not.toContainText("[PROVIDER] MOCK");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toContain("[NET] [PROVIDER] MOCK");

  await page.getByRole("button", { name: "清除 Log", exact: true }).click();
  await expect(log).toContainText("No log entries for selected filters.");
});
