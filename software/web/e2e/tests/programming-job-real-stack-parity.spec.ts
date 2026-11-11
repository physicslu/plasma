import { expect, test, type Page } from "@playwright/test";
import {
  expectProgrammingJobContract,
  expectProgrammingJobDesktopActionGeometry,
  programmingJob,
  programmingJobPresentation,
} from "./programming-job-test-helpers";

async function productionPanel(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  const panel = programmingJob(page, "production");
  await expectProgrammingJobContract(panel);
  return panel;
}

async function engineeringPanel(page: Page) {
  await page.goto("/engineering");
  await expect(page.locator(".engineeringSidebar")).toBeVisible();
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
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

    // One shared contract; EMode only tightens the field row padding for its 2-N labels.
    expect(ePresentation).toEqual({ ...pPresentation, field: { ...pPresentation.field, padding: "8px 10px" } });
    expect(ePresentation.status.position).toBe("static");
    await expectProgrammingJobDesktopActionGeometry(ePanel);
  });
}
