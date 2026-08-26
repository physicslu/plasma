import { expect, test, type Route } from "@playwright/test";
import { commitProductionSites, factoryConsoleHeading } from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
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

test("transient PPU status failure auto-recovers without reselecting FPS", async ({ page }) => {
  let statusRequests = 0;

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: { session_id: "0123456789abcdef0123456789abcdef", previous_session_cleared: false },
        }),
      });
      return;
    }
    if (path === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status`) {
      statusRequests += 1;
      if (statusRequests === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { error_code: "E2002", message: "temporary PPU communication failure" } }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live.getByText(/temporary PPU communication failure/)).toBeVisible();
  await expect.poll(() => statusRequests, { timeout: 8_000 }).toBeGreaterThanOrEqual(2);
  await expect(live.getByText(/temporary PPU communication failure/)).toHaveCount(0);
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
  await expect(page.getByText(/STATUS RESTORED · Mock PPU 01/)).toBeVisible();
});
