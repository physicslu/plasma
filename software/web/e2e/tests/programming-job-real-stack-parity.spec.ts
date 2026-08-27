import { expect, test, type Locator, type Page } from "@playwright/test";

function actionOrder(panel: Locator) {
  return panel.locator(":scope [data-programming-job-actions] > [data-programming-job-action]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-action")),
  );
}

function fieldOrder(panel: Locator) {
  return panel.locator(":scope [data-programming-job-fields] > [data-programming-job-field]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-field")),
  );
}

async function presentation(panel: Locator) {
  return panel.evaluate(element => {
    const read = (selector: string) => {
      const target = element.querySelector<HTMLElement>(selector);
      if (!target) throw new Error(`missing ${selector}`);
      const style = getComputedStyle(target);
      return {
        display: style.display,
        minHeight: style.minHeight,
        padding: style.padding,
        borderRadius: style.borderRadius,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        position: style.position,
      };
    };
    return {
      field: read('[data-programming-job-field="target"]'),
      operation: read(".programmingJobOperationChecks label"),
      checkbox: read(".programmingJobOperationChecks input"),
      start: read('[data-programming-job-action="start"]'),
      status: read('[data-programming-job-action="status"]'),
      abort: read('[data-programming-job-action="abort"]'),
    };
  });
}

async function productionPanel(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  const panel = page.getByRole("region", { name: "Production Programming Job" });
  await expect(panel).toBeVisible();
  return panel;
}

async function engineeringPanel(page: Page) {
  await page.goto("/engineering");
  await expect(page.locator(".engineeringSidebar")).toBeVisible();
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  const panel = page.getByRole("region", { name: "Engineering Programming Job" });
  await expect(panel).toBeVisible();
  return panel;
}

for (const width of [1200, 1680]) {
  test(`real stack keeps PMode and EMode Programming Job structurally identical at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => sessionStorage.clear());

    const pPanel = await productionPanel(page);
    expect(await fieldOrder(pPanel)).toEqual(["target", "image", "operations", "policy"]);
    expect(await actionOrder(pPanel)).toEqual(["start", "status", "abort"]);
    const pPresentation = await presentation(pPanel);

    const ePanel = await engineeringPanel(page);
    expect(await fieldOrder(ePanel)).toEqual(["target", "image", "operations", "policy"]);
    expect(await actionOrder(ePanel)).toEqual(["start", "status", "abort"]);
    const ePresentation = await presentation(ePanel);

    expect(ePresentation).toEqual(pPresentation);
    expect(ePresentation.status.position).toBe("static");

    const actionBar = ePanel.locator("[data-programming-job-actions]");
    const children = actionBar.locator(":scope > [data-programming-job-action]");
    await expect(children).toHaveCount(3);

    const start = await children.nth(0).boundingBox();
    const status = await children.nth(1).boundingBox();
    const abort = await children.nth(2).boundingBox();
    for (const box of [start, status, abort]) expect(box).not.toBeNull();
    expect(Math.abs(status!.width - 160)).toBeLessThanOrEqual(2);
    expect(start!.x + start!.width).toBeLessThan(status!.x);
    expect(status!.x + status!.width).toBeLessThan(abort!.x);
  });
}
