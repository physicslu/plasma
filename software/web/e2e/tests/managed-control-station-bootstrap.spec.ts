import { expect, test, type Page } from "@playwright/test";

// U10: the Console is Manager-managed only. Every Gateway path is rebased onto
// the same-origin `/api/manager/ppu` prefix; there is no standalone mode, no
// Browser-chosen Gateway URL and no routing discovery round-trip. These specs
// keep the regression guard that stale standalone Browser storage from an older
// Console (`plasma-api-mode` / `plasma-api-base`) is ignored and that no request
// ever reaches a direct Gateway.

const staleDirectGateway = "https://swpc.tail820e64.ts.net:8443";
const defaultRemoteGateway = "https://legacy-gateway.invalid";

async function seedLegacyStandaloneRouting(page: Page) {
  await page.addInitScript(({ directGateway }) => {
    window.localStorage.setItem("plasma-api-mode", "standalone");
    window.localStorage.setItem("plasma-api-base", directGateway);
  }, { directGateway: staleDirectGateway });
}

function observeGatewayRouting(page: Page) {
  const leakedGatewayRequests: string[] = [];
  const managedStatusRequests: string[] = [];
  page.on("request", request => {
    const url = request.url();
    if (url.startsWith(staleDirectGateway) || url.startsWith(defaultRemoteGateway)) {
      leakedGatewayRequests.push(url);
    }
    if (url.includes("/api/manager/ppu/api/status")) managedStatusRequests.push(url);
  });
  return { leakedGatewayRequests, managedStatusRequests };
}

async function routeManagedStatus(page: Page) {
  await page.route("**/api/manager/ppu/api/status", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, sites: [] }),
    });
  });
}

async function openConsole(page: Page) {
  await page.goto("/");
  // Hydrated: the root providers (Gateway transport, workspace session) are mounted.
  await expect(page.getByRole("group", { name: "Language" })).toHaveAttribute("aria-busy", "false");
}

/** A Gateway read aimed at any absolute Gateway URL lands on the managed prefix. */
async function gatewayRead(page: Page, gateway: string) {
  return await page.evaluate(async target => {
    const response = await fetch(`${target}/api/status`, { cache: "no-store" });
    return { status: response.status, ok: response.ok, url: response.url };
  }, gateway);
}

test("stale standalone Browser routing storage is ignored: Gateway reads go through the Manager", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  const { leakedGatewayRequests, managedStatusRequests } = observeGatewayRouting(page);
  await routeManagedStatus(page);

  await openConsole(page);
  for (const gateway of [staleDirectGateway, defaultRemoteGateway]) {
    expect(await gatewayRead(page, gateway)).toEqual({
      status: 200,
      ok: true,
      url: expect.stringMatching(/^http:\/\/127\.0\.0\.1:4173\/api\/manager\/ppu\/api\/status$/),
    });
  }
  expect(leakedGatewayRequests).toEqual([]);
  expect(managedStatusRequests.length).toBeGreaterThanOrEqual(2);
  // The stale keys are retired at load: never honoured, never re-published.
  expect(await page.evaluate(() => [
    window.localStorage.getItem("plasma-api-mode"),
    window.localStorage.getItem("plasma-api-base"),
  ])).toEqual([null, null]);
});

test("Managed routing stays exclusive during steady-state Browser traffic", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  const { leakedGatewayRequests, managedStatusRequests } = observeGatewayRouting(page);
  await routeManagedStatus(page);

  await openConsole(page);
  const statusCountAfterLoad = managedStatusRequests.length;
  const directAttempts: Array<{ status: number; ok: boolean; url: string }> = [];
  for (let attempt = 0; attempt < 2; attempt += 1) {
    directAttempts.push(await gatewayRead(page, staleDirectGateway));
    await page.waitForTimeout(250);
  }

  expect(leakedGatewayRequests).toEqual([]);
  expect(managedStatusRequests.length).toBeGreaterThanOrEqual(statusCountAfterLoad + 2);
  for (const directAttempt of directAttempts) {
    expect(directAttempt).toEqual({
      status: 200,
      ok: true,
      url: expect.stringContaining("/api/manager/ppu/api/status"),
    });
  }
});

test("Managed Control Station remains fail-closed when the BFF routing config is incomplete", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  const { leakedGatewayRequests } = observeGatewayRouting(page);
  await page.route("**/api/manager/ppu", async route => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        managed: true,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is not configured" },
      }),
    });
  });
  await page.route("**/api/manager/ppu/api/status", async route => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is not configured" } }),
    });
  });

  await openConsole(page);
  // Never a fallback to the stale direct Gateway: the read fails at the Manager.
  expect(await gatewayRead(page, staleDirectGateway)).toEqual({
    status: 503,
    ok: false,
    url: expect.stringContaining("/api/manager/ppu/api/status"),
  });
  expect(leakedGatewayRequests).toEqual([]);
});
