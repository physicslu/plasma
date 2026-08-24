import { expect, test, type Page, type Route } from "@playwright/test";

function catalog() {
  const siteCounts = [2, 4, 6, 8];
  const facilities = Array.from({ length: 3 }, (_, facilityIndex) => {
    const number = facilityIndex + 1;
    const facilityId = `mock-facility-${String(number).padStart(2, "0")}`;
    return {
      facility_id: facilityId,
      display_name: `Mock Facility ${String(number).padStart(2, "0")}`,
      ppus: siteCounts.map((siteCount, ppuIndex) => ({
        ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
        display_name: `Mock PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
        model: "MOCK-PPU",
        site_count: siteCount,
        provider: "mock",
      })),
    };
  });

  return {
    ok: true,
    provider: "mock",
    facility_count: facilities.length,
    ppu_count: facilities.reduce((count, facility) => count + facility.ppus.length, 0),
    site_count: facilities.reduce(
      (count, facility) => count + facility.ppus.reduce((ppuCount, ppu) => ppuCount + ppu.site_count, 0),
      0,
    ),
    facilities,
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
            session_id: "fps-selector-layout-session-00000000",
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

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(path);
    if (targetMatch && request.method() === "GET") {
      const facilityId = decodeURIComponent(targetMatch[1]);
      const ppuId = decodeURIComponent(targetMatch[2]);
      const ppuNumber = Number(/-ppu-(\d+)$/.exec(ppuId)?.[1] ?? 1);
      const siteCount = [2, 4, 6, 8][ppuNumber - 1] ?? 2;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          ppu: {
            ppu_id: ppuId,
            facility_id: facilityId,
            model: "MOCK-PPU",
            display_name: `Mock PPU ${String(ppuNumber).padStart(2, "0")}`,
            site_count: siteCount,
            enabled_site_count: siteCount,
            capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
          },
          sites: Array.from({ length: siteCount }, (_, index) => ({
            site_id: index + 1,
            enabled: true,
            state: "idle",
            current_job_id: null,
            queued_jobs: 0,
            interface: "mock",
            target: "MOCK-IC",
          })),
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function openProduction(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await installProductionCatalog(page);
  await page.goto("/fleet");
  await expect(page.getByRole("checkbox", { name: "mock-facility-01 mock-facility-01-ppu-01 SITE-01" })).toBeVisible();
}

async function selectorGeometry(page: Page) {
  return page.locator(".fpsSelector").evaluate(element => {
    const selector = element.getBoundingClientRect();
    const tree = element.querySelector<HTMLElement>(".fpsTree")!;
    const treeRect = tree.getBoundingClientRect();
    return {
      selectorTop: selector.top,
      selectorBottom: selector.bottom,
      selectorWidth: selector.width,
      selectorHeight: selector.height,
      treeHeight: treeRect.height,
      treeClientHeight: tree.clientHeight,
      treeScrollHeight: tree.scrollHeight,
      viewportHeight: window.innerHeight,
    };
  });
}

test("desktop FPS selector uses the remaining viewport instead of a 52vh tree cap", async ({ page }) => {
  await openProduction(page, { width: 1440, height: 900 });
  const geometry = await selectorGeometry(page);

  expect(geometry.selectorWidth).toBeGreaterThanOrEqual(319);
  expect(geometry.selectorHeight).toBeGreaterThanOrEqual(730);
  expect(geometry.selectorBottom).toBeLessThanOrEqual(geometry.viewportHeight + 1);
  expect(geometry.treeHeight).toBeGreaterThanOrEqual(geometry.selectorHeight * 0.62);
  expect(geometry.treeClientHeight).toBeGreaterThan(520);
  expect(geometry.treeScrollHeight).toBeGreaterThan(geometry.treeClientHeight);
});

test("iPad landscape keeps an operator-sized FPS column and collapses it back to a named compact rail", async ({ page }) => {
  await openProduction(page, { width: 1194, height: 834 });
  const expanded = await selectorGeometry(page);

  expect(expanded.selectorWidth).toBeGreaterThanOrEqual(319);
  expect(expanded.selectorHeight).toBeGreaterThanOrEqual(670);
  expect(expanded.selectorBottom).toBeLessThanOrEqual(expanded.viewportHeight + 1);

  await page.getByRole("button", { name: "收起選擇器" }).click();
  await expect(page.getByRole("button", { name: "展開選擇器" })).toBeVisible();
  await expect.poll(async () => {
    const box = await page.locator(".fpsSelector").boundingBox();
    return box?.width ?? Number.POSITIVE_INFINITY;
  }).toBeLessThanOrEqual(48);
  const collapsed = await page.locator(".fpsSelector").boundingBox();
  expect(collapsed?.height).toBeLessThanOrEqual(162);

  const railLabel = await page.locator(".fpsSelector").evaluate(element => {
    const style = getComputedStyle(element, "::after");
    return style.content.replace(/^['\"]|['\"]$/g, "");
  });
  expect(railLabel).toBe("FPS SELECTOR");
});
