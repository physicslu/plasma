import { expect, test, type Page, type Route } from "@playwright/test";
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

async function installGatewaySettings(page: Page) {
  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        rest_contract_version: "3",
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 3_000,
          ppu_retry_count: 1,
          ppu_response_budget_ms: 7_000,
        },
      }),
    });
  });
}

test("transient PPU status failure auto-recovers without reselecting FPS", async ({ page }) => {
  let statusRequests = 0;
  await installGatewaySettings(page);

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

test("Gateway-owned status window can exceed 5 seconds and PMode still recovers without reselecting FPS", async ({ page }) => {
  let statusRequests = 0;
  await installGatewaySettings(page);

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
        await new Promise(resolve => setTimeout(resolve, 6_000));
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            error: { error_code: "E2002", message: "Gateway PPU status retries exhausted" },
          }),
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

  const programming = page.getByRole("region", { name: "PROGRAMMING JOB" });
  const erase = programming.locator(".factoryOperationChecks label").filter({ hasText: /E/ }).getByRole("checkbox");
  const start = programming.getByRole("button", { name: /START PROGRAMMING/ });
  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });

  await erase.check();
  await expect(start).toBeDisabled();
  await expect(live.getByText(/Gateway PPU status retries exhausted/i)).toBeVisible({ timeout: 8_000 });
  await expect(live.getByText(/request timed out/i)).toHaveCount(0);
  await expect.poll(() => statusRequests, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
  await expect(live.getByText(/Gateway PPU status retries exhausted/i)).toHaveCount(0);
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
  await expect(page.getByText(/STATUS RESTORED · Mock PPU 01/)).toBeVisible();
  await expect(start).toBeEnabled();
});
