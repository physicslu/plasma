import { test, type Page, type Route } from "@playwright/test";
import {
  expectProgrammingJobContract,
  expectProgrammingJobDesktopActionGeometry,
  programmingJob,
  programmingJobPresentation,
} from "./programming-job-test-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

const catalog = {
  ok: true,
  provider: "mock",
  facility_count: 1,
  ppu_count: 1,
  site_count: 2,
  programming_asset_scope: "connection-session-and-ppu",
  facilities: [{
    facility_id: facilityId,
    display_name: "Mock Facility 01",
    ppus: [{ ppu_id: ppuId, display_name: "Mock PPU 01", model: "MOCK-PPU", site_count: 2, provider: "mock" }],
  }],
};

const status = {
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

async function installMockProvider(page: Page) {
  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 10_000,
          ppu_retry_count: 3,
          ppu_response_budget_ms: 47_000,
        },
      }),
    });
  });

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog) });
      return;
    }
    if (/\/api\/engineering\/targets\/[^/]+\/[^/]+\/api\/status$/.test(url.pathname) && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

for (const width of [1200, 1680]) {
  test(`PMode and EMode render one shared Programming Job contract at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => sessionStorage.clear());
    await installMockProvider(page);

    await page.goto("/fleet");
    const pPanel = programmingJob(page, "production");
    await expectProgrammingJobContract(pPanel);
    const pPresentation = await programmingJobPresentation(pPanel);

    await page.goto("/engineering");
    await page.locator(".engineeringWorkspace nav button").nth(2).click();
    const ePanel = programmingJob(page, "engineering");
    await expectProgrammingJobContract(ePanel);
    const ePresentation = await programmingJobPresentation(ePanel);

    if (JSON.stringify(ePresentation) !== JSON.stringify(pPresentation)) {
      throw new Error("PMode and EMode Programming Job presentation diverged");
    }
    if (ePresentation.status.position !== "static") {
      throw new Error(`Programming Job status must remain in normal flow, got ${ePresentation.status.position}`);
    }
    await expectProgrammingJobDesktopActionGeometry(ePanel);
  });
}
