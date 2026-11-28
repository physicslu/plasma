import { expect, test, type Locator, type Page } from "@playwright/test";
import { Z2, mockManager } from "./managed-programming-helpers";
import { programmingJob, programmingJobField } from "./programming-job-test-helpers";

// U10: the Console is Manager-managed only. Topology comes from the Mock
// Manager at the Browser boundary (managed-programming-helpers.ts).
async function openEngineeringProgramming(page: Page) {
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2], siteCount: 2 }] });
  await page.goto("/engineering");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  await expect(page.getByLabel("Engineering PPU", { exact: true })).toBeVisible();
}

async function rowMetrics(row: Locator) {
  return row.evaluate(element => {
    const children = Array.from(element.children);
    const label = children[0] as HTMLElement;
    const control = children[1] as HTMLElement;
    const rowBox = element.getBoundingClientRect();
    const controlBox = control.getBoundingClientRect();
    const labelBox = label.getBoundingClientRect();
    const style = getComputedStyle(label);
    return {
      gap: controlBox.left - labelBox.right,
      controlX: controlBox.left,
      controlOffset: controlBox.left - rowBox.left,
      labelOffset: labelBox.left - rowBox.left,
      textAlign: style.textAlign,
      justifySelf: style.justifySelf,
    };
  });
}

async function stackedRowMetrics(row: Locator) {
  return row.evaluate(element => {
    const children = Array.from(element.children);
    const label = children[0] as HTMLElement;
    const control = children[1] as HTMLElement;
    const rowBox = element.getBoundingClientRect();
    const labelBox = label.getBoundingClientRect();
    const controlBox = control.getBoundingClientRect();
    const rowStyle = getComputedStyle(element);
    const labelStyle = getComputedStyle(label);
    const container = element.closest<HTMLElement>(".engineeringProgrammingV2");
    return {
      viewportWidth: window.innerWidth,
      containerWidth: container?.getBoundingClientRect().width ?? 0,
      rowGap: rowStyle.rowGap,
      labelOffset: labelBox.left - rowBox.left,
      controlOffset: controlBox.left - rowBox.left,
      verticalGap: controlBox.top - labelBox.bottom,
      textAlign: labelStyle.textAlign,
      justifySelf: labelStyle.justifySelf,
    };
  });
}

function expectRightAlignedRail(metric: Awaited<ReturnType<typeof rowMetrics>>, minOffset: number, maxOffset: number) {
  expect(metric.gap).toBeGreaterThanOrEqual(6);
  expect(metric.gap).toBeLessThanOrEqual(14);
  expect(metric.controlOffset).toBeGreaterThanOrEqual(minOffset);
  expect(metric.controlOffset).toBeLessThanOrEqual(maxOffset);
  expect(metric.textAlign).toBe("right");
  expect(metric.justifySelf).toBe("end");
}

function expectProgrammingJobRail(metric: Awaited<ReturnType<typeof rowMetrics>>) {
  expect(metric.labelOffset).toBeGreaterThanOrEqual(8);
  expect(metric.labelOffset).toBeLessThanOrEqual(12);
  // EMode 2-N labels: 10px padding + 180px label column + 10px gap.
  expect(metric.controlOffset).toBeGreaterThanOrEqual(198);
  expect(metric.controlOffset).toBeLessThanOrEqual(202);
  expect(metric.textAlign).toBe("left");
  expect(metric.justifySelf).toBe("stretch");
}

test("Engineering targeting remains compact while shared Programming Job uses the operator density rail", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await openEngineeringProgramming(page);

  const facility = await rowMetrics(page.locator(".targetingCard .workflowField").nth(0));
  const ppu = await rowMetrics(page.locator(".targetingCard .workflowField").nth(1));
  const job = programmingJob(page, "engineering");
  const fields = await Promise.all(["target", "image", "operations", "policy"].map(field => rowMetrics(programmingJobField(job, field as "target" | "image" | "operations" | "policy"))));

  for (const metric of [facility, ppu]) expectRightAlignedRail(metric, 118, 122);
  for (const metric of fields) expectProgrammingJobRail(metric);
  expect(Math.max(...fields.map(metric => metric.controlX)) - Math.min(...fields.map(metric => metric.controlX))).toBeLessThanOrEqual(2);
});

test("Engineering targeting stacks when the Programming container narrows before the viewport mobile breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 980, height: 900 });
  await openEngineeringProgramming(page);

  const facility = await stackedRowMetrics(page.locator(".targetingCard .workflowField").nth(0));
  const ppu = await stackedRowMetrics(page.locator(".targetingCard .workflowField").nth(1));

  for (const metric of [facility, ppu]) {
    expect(metric.viewportWidth).toBeGreaterThan(760);
    expect(metric.containerWidth).toBeLessThanOrEqual(760);
    expect(metric.rowGap).toBe("12px");
    expect(metric.verticalGap).toBeGreaterThanOrEqual(10);
    expect(Math.abs(metric.labelOffset - metric.controlOffset)).toBeLessThanOrEqual(2);
    expect(metric.textAlign).toBe("left");
    expect(metric.justifySelf).toBe("start");
  }
});
