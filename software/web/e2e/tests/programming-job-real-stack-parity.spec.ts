import { expect, test, type Page } from "@playwright/test";
import { managed, openEngineering, selectEngineeringIc } from "./mock-cd-managed-helpers";
import {
  expectProgrammingJobContract,
  expectProgrammingJobDesktopActionGeometry,
  programmingJob,
  programmingJobPresentation,
} from "./programming-job-test-helpers";

// U10: both managed Consoles (PMode Factory Console and EMode Single PPU) on
// the real Manager-backed stack present ONE Programming Job contract.

async function productionPanel(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  await expect(page.locator('main[data-programming-backend="manager"]')).toBeVisible();
  // A Production Site of a managed PPU plus the chosen IC's Route supply the E / P / V operations.
  await expect(page.locator(".productionTreeFacility").first()).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => document.querySelectorAll("details").forEach(item => { item.open = true; }));
  await page.getByRole("checkbox", { name: `Production Set ${managed.facilityId} ${managed.consoleAlias} SITE-01` }).check();
  await page.getByRole("button", { name: "SET PRODUCTION SITES", exact: true }).click();
  const panel = programmingJob(page, "production");
  await panel.getByLabel("Target IC").fill(managed.icpn);
  await page.getByRole("option", { name: new RegExp(`^${managed.icpn}(?:\\s|$)`) }).first().click();
  await expectProgrammingJobContract(panel);
  return panel;
}

async function engineeringPanel(page: Page) {
  await openEngineering(page);
  await selectEngineeringIc(page);
  const panel = programmingJob(page, "engineering");
  await expectProgrammingJobContract(panel);
  return panel;
}

for (const width of [1200, 1680]) {
  test(`real stack keeps PMode and EMode on one Programming Job contract at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => sessionStorage.clear());

    const pPanel = await productionPanel(page);
    const pPresentation = await programmingJobPresentation(pPanel);

    const ePanel = await engineeringPanel(page);
    const ePresentation = await programmingJobPresentation(ePanel);

    expect(ePresentation).toEqual(pPresentation);
    expect(ePresentation.status.position).toBe("static");
    await expectProgrammingJobDesktopActionGeometry(ePanel);
  });
}
