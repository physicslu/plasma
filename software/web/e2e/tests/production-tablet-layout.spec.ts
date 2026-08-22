import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";

function catalog() {
  const siteCounts = [2, 4, 6, 8];
  const facilities = Array.from({ length: 3 }, (_, facilityIndex) => {
    const number = facilityIndex + 1;
    const id = `mock-facility-${String(number).padStart(2, "0")}`;
    return {
      facility_id: id,
      display_name: `Mock Facility ${String(number).padStart(2, "0")}`,
      ppus: siteCounts.map((siteCount, ppuIndex) => ({
        ppu_id: `${id}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
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
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
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
            session_id: "tablet-layout-session-000000000000",
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
            facility_id: decodeURIComponent(targetMatch[1]),
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

test("Production batch toolbar follows its available width on iPad landscape", async ({ page }) => {
  // iPad Pro 11-inch landscape CSS viewport. The expanded FPS selector leaves
  // substantially less width for the Production main panel than the viewport
  // itself, which is the regression this test protects.
  await page.setViewportSize({ width: 1194, height: 834 });
  await installProductionCatalog(page);
  await page.goto("/fleet");

  const toolbar = page.getByRole("region", { name: "Batch operation toolbar" });
  await expect(toolbar).toBeVisible();
  await expect(page.getByRole("checkbox", { name: `${facilityId} ${facilityId}-ppu-01 SITE-01` })).toBeVisible();

  const expanded = await toolbar.evaluate(element => {
    const toolbarRect = element.getBoundingClientRect();
    const image = element.querySelector<HTMLElement>(".programmingBatchFile")!;
    const operations = element.querySelector<HTMLElement>(".programmingBatchOperations")!;
    const actions = element.querySelector<HTMLElement>(".programmingBatchActions")!;
    const imageRect = image.getBoundingClientRect();
    const operationsRect = operations.getBoundingClientRect();
    const actionsRect = actions.getBoundingClientRect();
    const operationTops = [...operations.querySelectorAll<HTMLElement>("label")].map(label => label.getBoundingClientRect().top);

    return {
      areas: getComputedStyle(element).gridTemplateAreas,
      operationWrap: getComputedStyle(operations).flexWrap,
      operationTopSpread: Math.max(...operationTops) - Math.min(...operationTops),
      toolbarRight: toolbarRect.right,
      actionsRight: actionsRect.right,
      imageBottom: imageRect.bottom,
      operationsBottom: operationsRect.bottom,
      actionsTop: actionsRect.top,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });

  expect(expanded.areas).toBe('"image operations" "actions actions"');
  expect(expanded.operationWrap).toBe("nowrap");
  expect(expanded.operationTopSpread).toBeLessThanOrEqual(1);
  expect(expanded.actionsTop).toBeGreaterThanOrEqual(Math.max(expanded.imageBottom, expanded.operationsBottom) - 1);
  expect(expanded.actionsRight).toBeLessThanOrEqual(expanded.toolbarRight + 1);
  expect(expanded.scrollWidth).toBeLessThanOrEqual(expanded.clientWidth + 1);

  await page.getByRole("button", { name: "收起選擇器" }).click();
  await expect(page.getByRole("button", { name: "展開選擇器" })).toBeVisible();
  await page.waitForTimeout(220);

  const collapsed = await toolbar.evaluate(element => ({
    areas: getComputedStyle(element).gridTemplateAreas,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));

  expect(collapsed.areas).toBe('"image operations actions"');
  expect(collapsed.scrollWidth).toBeLessThanOrEqual(collapsed.clientWidth + 1);
});
