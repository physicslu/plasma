import { expect, test, type Page } from "@playwright/test";
import { mockFleet, mockManager } from "./managed-programming-helpers";
import { factoryConsoleHeading, programmingJob } from "./production-console-helpers";

// U10: the Console is Manager-managed only. Three Facilities × four PPUs
// (2/4/6/8 Sites) come from the Mock Manager Registry / Fleet.
async function installProductionCatalog(page: Page) {
  await mockManager(page, { ppus: mockFleet() });
}

async function expectConstrainedProgrammingJob(page: Page) {
  const job = programmingJob(page);
  await expect(job).toBeVisible();

  const layout = await job.evaluate(element => {
    const panel = element.getBoundingClientRect();
    const grid = element.querySelector<HTMLElement>("[data-programming-job-fields]")!;
    const operations = element.querySelector<HTMLElement>('[data-programming-job-field="operations"] [role="group"]')!;
    const actionBar = element.querySelector<HTMLElement>("[data-programming-job-actions]")!;
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

  const selection = page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" });
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
