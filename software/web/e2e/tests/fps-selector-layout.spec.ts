import { expect, test, type Page, type Route } from "@playwright/test";
import { expandProductionTree, factoryConsoleHeading } from "./production-console-helpers";

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

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function openProduction(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await installProductionCatalog(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await expandProductionTree(page);
  await expect(page.getByRole("checkbox", {
    name: "Production Set mock-facility-01 mock-facility-01-ppu-01 SITE-01",
  })).toBeVisible();
}

test("desktop Production Site Selection uses a wide multi-column tree with bounded scrolling", async ({ page }) => {
  await openProduction(page, { width: 1440, height: 900 });

  const geometry = await page.locator(".productionSiteSelection").evaluate(element => {
    const panel = element.getBoundingClientRect();
    const tree = element.querySelector<HTMLElement>(".productionTree")!;
    const treeStyle = getComputedStyle(tree);
    return {
      panelWidth: panel.width,
      treeWidth: tree.getBoundingClientRect().width,
      treeHeight: tree.getBoundingClientRect().height,
      treeColumns: treeStyle.gridTemplateColumns.split(" ").filter(Boolean).length,
      treeOverflowY: treeStyle.overflowY,
      treeScrollWidth: tree.scrollWidth,
      treeClientWidth: tree.clientWidth,
    };
  });

  expect(geometry.panelWidth).toBeGreaterThan(1300);
  expect(geometry.treeWidth).toBeGreaterThan(1280);
  expect(geometry.treeColumns).toBeGreaterThanOrEqual(3);
  expect(geometry.treeHeight).toBeLessThanOrEqual(321);
  expect(geometry.treeOverflowY).toBe("auto");
  expect(geometry.treeScrollWidth).toBeLessThanOrEqual(geometry.treeClientWidth + 1);
});

test("iPad landscape hides only the Production Site Selection body", async ({ page }) => {
  await openProduction(page, { width: 1194, height: 834 });

  const selection = page.getByRole("region", { name: "PRODUCTION SITE SELECTION" });
  const programmingJob = page.getByRole("region", { name: "PROGRAMMING JOB" });
  const liveStatus = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(selection.locator(".operatorPanelBody")).toBeVisible();
  await expect(programmingJob).toBeVisible();
  await expect(liveStatus).toBeVisible();

  await selection.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(selection.locator(".operatorPanelBody")).toBeHidden();
  await expect(selection.getByRole("button", { name: /展開|Show/ })).toBeVisible();
  await expect(programmingJob).toBeVisible();
  await expect(liveStatus).toBeVisible();
});
