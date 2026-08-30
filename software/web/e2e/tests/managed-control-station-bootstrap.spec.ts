import { expect, test } from "@playwright/test";

const staleDirectGateway = "https://swpc.tail820e64.ts.net:8443";
const defaultRemoteGateway = "https://plasma.open4th.com";

async function seedLegacyStandaloneRouting(page: import("@playwright/test").Page) {
  await page.addInitScript(({ directGateway }) => {
    window.localStorage.setItem("plasma-api-mode", "standalone");
    window.localStorage.setItem("plasma-api-base", directGateway);
  }, { directGateway: staleDirectGateway });
}

async function expectManagedBrowserRouting(page: import("@playwright/test").Page) {
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-mode")))
    .toBe("managed");
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-base")))
    .toMatch(/\/api\/manager\/ppu$/);
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-base")))
    .not.toBe(staleDirectGateway);
}

test("Managed Control Station overrides stale standalone Browser routing", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  await page.route("**/api/manager/ppu", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, managed: true, configured: true, ppu_alias: "swpc" }),
    });
  });

  await page.goto("/");
  await expectManagedBrowserRouting(page);
});

test("Gateway requests stay inside the Browser until Managed routing discovery resolves", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);

  const leakedGatewayRequests: string[] = [];
  page.on("request", request => {
    const url = request.url();
    if (url.startsWith(staleDirectGateway) || url.startsWith(defaultRemoteGateway)) {
      leakedGatewayRequests.push(url);
    }
  });

  let releaseDiscovery!: () => void;
  const discoveryReleased = new Promise<void>(resolve => { releaseDiscovery = resolve; });
  let observeDiscovery!: () => void;
  const discoveryObserved = new Promise<void>(resolve => { observeDiscovery = resolve; });

  await page.route("**/api/manager/ppu", async route => {
    observeDiscovery();
    await discoveryReleased;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, managed: true, configured: true, ppu_alias: "swpc" }),
    });
  });

  const navigation = page.goto("/");
  await discoveryObserved;

  const blocked = await page.evaluate(async ({ gateways }) => {
    return await Promise.all(gateways.map(async gateway => {
      const response = await fetch(`${gateway}/api/status`, { cache: "no-store" });
      return {
        status: response.status,
        payload: await response.json() as { error?: { error_code?: string } },
      };
    }));
  }, { gateways: [staleDirectGateway, defaultRemoteGateway] });

  expect(blocked).toEqual([
    { status: 503, payload: { ok: false, error: { error_code: "routing_unresolved", message: "Gateway routing is not resolved yet" } } },
    { status: 503, payload: { ok: false, error: { error_code: "routing_unresolved", message: "Gateway routing is not resolved yet" } } },
  ]);
  expect(leakedGatewayRequests).toEqual([]);

  releaseDiscovery();
  await navigation;
  await expectManagedBrowserRouting(page);
  expect(leakedGatewayRequests).toEqual([]);
});

test("Managed Control Station remains fail-closed when the BFF routing config is incomplete", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
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

  await page.goto("/");
  await expectManagedBrowserRouting(page);
});
