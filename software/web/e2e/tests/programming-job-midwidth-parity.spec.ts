import { expect, test, type Page } from "@playwright/test";
import { Z2, mockManager } from "./managed-programming-helpers";
import { chooseTestTarget, commitProductionSites } from "./production-console-helpers";
import {
  expectProgrammingJobContract,
  expectProgrammingJobDesktopActionGeometry,
  programmingJob,
  programmingJobPresentation,
} from "./programming-job-test-helpers";

// U10: the Console is Manager-managed only; the Mock Manager answers at the
// Browser boundary (managed-programming-helpers.ts).
async function installMockProvider(page: Page) {
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2], siteCount: 2 }] });
}

for (const width of [1200, 1680]) {
  test(`PMode and EMode render one shared Programming Job contract at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => sessionStorage.clear());
    await installMockProvider(page);

    await page.goto("/fleet");
    // The managed PMode lists the Route's operations once Production Sites
    // and a Target IC are chosen.
    await commitProductionSites(page, "lab", "z2", [1, 2]);
    await chooseTestTarget(page);
    const pPanel = programmingJob(page, "production");
    await expectProgrammingJobContract(pPanel);
    const pPresentation = await programmingJobPresentation(pPanel);

    await page.goto("/engineering");
    await page.locator(".engineeringWorkspace nav button").nth(2).click();
    const ePanel = programmingJob(page, "engineering");
    await expectProgrammingJobContract(ePanel);
    const ePresentation = await programmingJobPresentation(ePanel);

    expect(ePresentation).toEqual(pPresentation);
    expect(ePresentation.status.position).toBe("static");
    await expectProgrammingJobDesktopActionGeometry(ePanel);
  });
}
