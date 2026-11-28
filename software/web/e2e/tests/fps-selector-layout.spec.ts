import { expect, test, type Page } from "@playwright/test";
import { mockFleet, mockManager } from "./managed-programming-helpers";
import { expandProductionTree, factoryConsoleHeading } from "./production-console-helpers";

// U10: the Console is Manager-managed only. Three Facilities × four PPUs
// (2/4/6/8 Sites) come from the Mock Manager Registry / Fleet.
async function installProductionCatalog(page: Page) {
  await mockManager(page, { ppus: mockFleet() });
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

  const selection = page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" });
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
