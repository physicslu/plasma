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

function observeGatewayRouting(page: import("@playwright/test").Page) {
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

test("Gateway reads stay inside the Browser until Managed routing discovery resolves", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  const { leakedGatewayRequests, managedStatusRequests } = observeGatewayRouting(page);

  let releaseDiscovery!: () => void;
  const discoveryReleased = new Promise<void>(resolve => { releaseDiscovery = resolve; });
  let observeDiscovery!: () => void;
  const discoveryObserved = new Promise<void>(resolve => { observeDiscovery = resolve; });

  await page.route("**/api/manager/ppu/api/status", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, sites: [] }),
    });
  });
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

  await page.evaluate(({ gateways }) => {
    const scope = window as typeof window & {
      __plasmaBootstrapReads?: Promise<Array<{ status: number; ok: boolean }>>;
    };
    scope.__plasmaBootstrapReads = Promise.all(gateways.map(async gateway => {
      const response = await fetch(`${gateway}/api/status`, { cache: "no-store" });
      return { status: response.status, ok: response.ok };
    }));
  }, { gateways: [staleDirectGateway, defaultRemoteGateway] });

  await page.waitForTimeout(50);
  expect(leakedGatewayRequests).toEqual([]);

  releaseDiscovery();
  await navigation;
  const reads = await page.evaluate(async () => {
    const scope = window as typeof window & {
      __plasmaBootstrapReads?: Promise<Array<{ status: number; ok: boolean }>>;
    };
    return await scope.__plasmaBootstrapReads;
  });

  expect(reads).toEqual([
    { status: 200, ok: true },
    { status: 200, ok: true },
  ]);
  await expectManagedBrowserRouting(page);
  expect(leakedGatewayRequests).toEqual([]);
  expect(managedStatusRequests.length).toBeGreaterThanOrEqual(2);
});

test("Managed routing stays exclusive during steady-state polling", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  const { leakedGatewayRequests, managedStatusRequests } = observeGatewayRouting(page);

  await page.route("**/api/manager/ppu/api/status", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, sites: [] }),
    });
  });
  await page.route("**/api/manager/ppu", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, managed: true, configured: true, ppu_alias: "swpc" }),
    });
  });

  await page.goto("/");
  await expectManagedBrowserRouting(page);

  const statusCountAfterBootstrap = managedStatusRequests.length;
  await page.waitForTimeout(1_600);

  expect(leakedGatewayRequests).toEqual([]);
  expect(managedStatusRequests.length).toBeGreaterThan(statusCountAfterBootstrap);

  const directAttempt = await page.evaluate(async directGateway => {
    const response = await fetch(`${directGateway}/api/status`, { cache: "no-store" });
    return { status: response.status, ok: response.ok, url: response.url };
  }, staleDirectGateway);

  expect(directAttempt).toEqual({
    status: 200,
    ok: true,
    url: expect.stringContaining("/api/manager/ppu/api/status"),
  });
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
