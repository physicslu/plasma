import { expect, test, type Page, type Route } from "@playwright/test";
import { factoryConsoleHeading } from "./production-console-helpers";

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

  return { ok: true, provider: "mock", facility_count: 3, ppu_count: 12, site_count: 60, facilities };
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
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function expectConstrainedProgrammingJob(page: Page) {
  const job = page.getByRole("region", { name: "PROGRAMMING JOB" });
  await expect(job).toBeVisible();

  const layout = await job.evaluate(element => {
    const panel = element.getBoundingClientRect();
    const grid = element.querySelector<HTMLElement>(".factoryJobGrid")!;
    const operations = element.querySelector<HTMLElement>(".factoryOperationChecks")!;
    const actionBar = element.querySelector<HTMLElement>(".factoryActionBar")!;
    const operationTops = [...operations.querySelectorAll<HTMLElement>("label")].map(label => label.getBoundingClientRect().top);
    const actions = [...actionBar.querySelectorAll<HTMLElement>("button")].map(button => button.getBoundingClientRect());
    return {
      gridColumns: getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length,
      operationWrap: getComputedStyle(operations).flexWrap,
      operationTopSpread: Math.max(...operationTops) - Math.min(...operationTops),
      panelLeft: panel.left,
      panelRight: panel.right,
      actionLefts: actions.map(rect => rect.left),
      actionRights: actions.map(rect => rect.right),
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });

  expect(layout.gridColumns).toBeGreaterThanOrEqual(1);
  expect(layout.operationWrap).toBe("nowrap");
  expect(layout.operationTopSpread).toBeLessThanOrEqual(1);
  expect(Math.min(...layout.actionLefts)).toBeGreaterThanOrEqual(layout.panelLeft - 1);
  expect(Math.max(...layout.actionRights)).toBeLessThanOrEqual(layout.panelRight + 1);
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1);
}

async function openProduction(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await installProductionCatalog(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
}

test("Production Programming Job stays contained on iPad landscape", async ({ page }) => {
  await openProduction(page, { width: 1194, height: 834 });
  await expectConstrainedProgrammingJob(page);

  const selection = page.getByRole("region", { name: "PRODUCTION SITE SELECTION" });
  await selection.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(selection.locator(".operatorPanelBody")).toBeHidden();
  await expectConstrainedProgrammingJob(page);
});

test("Production Programming Job follows a constrained content column at a wide viewport", async ({ page }) => {
  await openProduction(page, { width: 1440, height: 900 });

  const shell = page.locator(".factoryConsoleShell");
  await shell.evaluate(element => {
    const node = element as HTMLElement;
    node.style.width = "1040px";
    node.style.maxWidth = "1040px";
    node.style.marginLeft = "0";
  });

  await expect.poll(() => shell.evaluate(element => element.clientWidth)).toBeLessThanOrEqual(1040);
  await expectConstrainedProgrammingJob(page);
});
