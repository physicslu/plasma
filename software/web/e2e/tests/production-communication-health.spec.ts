import { expect, test, type Page, type Route } from "@playwright/test";
import { commitProductionSites } from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

type StatusMode = "ok" | "ppu-http-failure" | "transport-failure";
type CatalogMode = "ok" | "provider-http-failure";

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

async function installHealthMock(
  page: Page,
  options: { statusMode?: StatusMode; catalogMode?: CatalogMode } = {},
) {
  const statusMode = options.statusMode ?? "ok";
  const catalogMode = options.catalogMode ?? "ok";

  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 5_000,
          ppu_retry_count: 0,
          ppu_response_budget_ms: 5_000,
        },
      }),
    });
  });

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
      if (catalogMode === "provider-http-failure") {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            ok: false,
            error: { error_code: "E3001", message: "Engineering provider unavailable" },
          }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status`) {
      if (statusMode === "transport-failure") {
        await route.abort("failed");
        return;
      }
      if (statusMode === "ppu-http-failure") {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            ok: false,
            error: { error_code: "E2002", message: "PPU request timed out" },
          }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

function communicationHealth(page: Page) {
  return page.getByLabel("Factory communication health");
}

test("healthy selected PPU reports Gateway ONLINE and PPU READY separately", async ({ page }) => {
  await installHealthMock(page);
  await page.goto("/fleet");
  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU —");

  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU 1/1 READY");
});

test("PPU HTTP communication failure keeps Gateway ONLINE and marks PPU DEGRADED", async ({ page }) => {
  await installHealthMock(page, { statusMode: "ppu-http-failure" });
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);

  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU 0/1 READY · DEGRADED");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
});

test("transport failure marks Gateway UNREACHABLE and PPU UNKNOWN", async ({ page }) => {
  await installHealthMock(page, { statusMode: "transport-failure" });
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);

  await expect(communicationHealth(page)).toContainText("Gateway UNREACHABLE · PPU UNKNOWN");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
});

test("provider HTTP failure keeps Gateway ONLINE and reports PPU UNAVAILABLE", async ({ page }) => {
  await installHealthMock(page, { catalogMode: "provider-http-failure" });
  await page.goto("/fleet");

  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU UNAVAILABLE");
  await expect(page.getByRole("status")).toContainText(/Mock Provider|provider/i);
});
