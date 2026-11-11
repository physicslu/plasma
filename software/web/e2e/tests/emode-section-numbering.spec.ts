import { expect, test } from "@playwright/test";
import { FIRMWARE, Z2, mockManager } from "./managed-programming-helpers";

// Host-only Console acceptance of the EMode section numbering
// (1 / 2 / 2-1 … 2-4 / 3 / 4) on the formal Manager backend. Mock Manager at
// the Browser boundary: NOT physical PPU, FPGA or DUT evidence.

test("EMode sections are numbered 1 / 2 (2-1 … 2-4) / 3 / 4 and keep READ, Batch Attempts and the run view", async ({ page }, testInfo) => {
  await mockManager(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: /Programming|燒錄/ }).first().click();
  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE");

  // 1 and 3 are real heading text; 2 and 4 are the OperatorPanel number.
  await expect(workspace.locator(".targetingCard > header")).toContainText("1. SYSTEM SETUP & TARGETING");
  const job = page.getByRole("region", { name: "Engineering Programming Job" });
  await expect(job.locator(".operatorPanelTitle")).toHaveText(/^2\.\s*PROGRAMMING JOB$/);
  await expect(workspace.locator(".liveSiteStatus > header > span")).toHaveText("3. LIVE SITE STATUS");
  await expect(workspace.locator(".operatorLogCard .operatorPanelTitle")).toHaveText(/^4\.\s*ENGINEERING JOB LOG$/);
  // Exactly one number per title.
  await expect(workspace.getByText(/2\.\s*2\.|1\.\s*1\.|3\.\s*3\.|4\.\s*4\./)).toHaveCount(0);

  await expect(job.locator('[data-programming-job-field="target"] > strong')).toHaveText("2-1. Target IC");
  await expect(job.locator('[data-programming-job-field="image"] > strong')).toHaveText("2-2. Programming Source");
  await expect(job.locator('[data-programming-job-field="operations"] > strong')).toHaveText("2-3. Operations");
  await expect(job.locator('[data-programming-job-field="policy"] > strong')).toHaveText("2-4. Batch Policy");

  // One label column; Source selector, file picker and Batch Policy share the
  // Operator control height; the IC picker keeps its EMode size (never shrunk).
  const labelLeft = await job.locator(".programmingJobField > strong")
    .evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().left)));
  expect(new Set(labelLeft).size).toBe(1);
  const heights = await job.locator(".programmingSourceSelector, .programmingJobImageControl, .programmingJobPolicyControls input, .programmingJobPolicyControls select")
    .evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().height)));
  expect(heights, `control heights ${heights.join(", ")}`).toEqual(heights.map(() => 32));
  const picker = await job.locator(".icPickerInput").evaluate(node => ({
    height: node.getBoundingClientRect().height,
    inputSize: parseFloat(getComputedStyle(node.querySelector("input")!).fontSize),
  }));
  expect(picker.height).toBeGreaterThanOrEqual(40);
  expect(picker.inputSize).toBeGreaterThanOrEqual(12);
  // Field labels keep the shared Operator label typography and one line each.
  const labels = await job.locator(".programmingJobField > strong").evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node);
    return { size: style.fontSize, weight: style.fontWeight, clipped: node.scrollWidth > node.clientWidth };
  }));
  expect(labels).toEqual(labels.map(() => ({ size: "11px", weight: "800", clipped: false })));

  await job.getByPlaceholder("Search ICPN / IC identifier...").fill("STM32F103");
  await job.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await workspace.getByLabel("Select SITE 2 for programming").check();
  await job.getByLabel("Engineering Programming Image file").setInputFiles(
    { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });

  // The numbering removes nothing: E / P / V, per-Site READ, Batch Attempts, run view.
  for (const name of ["erase", "program", "verify"]) {
    await expect(job.getByLabel(`Engineering operation ${name}`)).toBeChecked();
  }
  const live = workspace.getByRole("region", { name: "Engineering Site selection" });
  await expect(live.getByRole("button", { name: /^Read SITE \d+ Flash$/ })).toHaveCount(1);
  await expect(workspace.getByTestId("read-memory")).toHaveCount(0);
  // The file picker sits in the control column, under the Source selector.
  const selectorBox = (await job.locator(".programmingSourceSelector").boundingBox())!;
  const fileBox = (await job.locator(".programmingJobImageControl").boundingBox())!;
  expect(Math.abs(fileBox.x - selectorBox.x)).toBeLessThanOrEqual(1);
  expect(fileBox.y).toBeGreaterThan(selectorBox.y + selectorBox.height);
  expect(fileBox.width).toBeGreaterThan(400);
  await page.screenshot({ path: testInfo.outputPath("emode-1680-ready.png"), fullPage: true });

  await job.getByRole("button", { name: /START PROGRAMMING/ }).click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByTestId("batch-attempts")).toBeVisible();
  await expect(workspace.getByLabel("Programming run", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("emode-1680-pass.png"), fullPage: true });

  // Narrow container: the 2-N fields stack without horizontal overflow.
  await page.setViewportSize({ width: 820, height: 900 });
  await expect(job.locator('[data-programming-job-field="policy"] > strong')).toBeVisible();
  expect(await job.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("emode-820-pass.png"), fullPage: true });
});

// The Programming Job is shared: PMode keeps its own numbering and metrics.
for (const width of [1680, 820]) {
  test(`PMode Programming Job keeps 1 … 4 and its shared field metrics at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockManager(page, { ppus: [Z2] });
    await page.goto("/fleet");
    await expect(page.locator('main[data-programming-backend="manager"]')).toBeVisible();
    await expect(page.locator(".productionTreeFacility").first()).toBeVisible();
    await page.evaluate(() => document.querySelectorAll("details").forEach(item => { item.open = true; }));
    await page.getByLabel("Production Set lab z2 SITE-02").check();
    await page.getByRole("button", { name: "SET PRODUCTION SITES" }).click();
    const job = page.getByRole("region", { name: "Production Programming Job" });
    await job.getByLabel("Target IC").fill("STM32F103");
    await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
    await job.getByLabel("Production Programming Image file").setInputFiles(
      { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });

    await expect(job.locator(".operatorPanelTitle")).toHaveText(/^2\.\s*PROGRAMMING JOB$/);
    await expect(job.locator('[data-programming-job-field="target"] > strong')).toHaveText("1. Target IC");
    await expect(job.locator('[data-programming-job-field="image"] > strong')).toHaveText("2. Programming Source");
    await expect(job.locator('[data-programming-job-field="operations"] > strong')).toHaveText("3. Operations");
    await expect(job.locator('[data-programming-job-field="policy"] > strong')).toHaveText("4. Batch Policy");
    await expect(job.getByText(/2-[1-4]\./)).toHaveCount(0);

    // Values measured on main e3e3b72c2: the EMode label column never leaks into PMode.
    const fields = await job.locator(".programmingJobField").evaluateAll(nodes => nodes.map(node => {
      const style = getComputedStyle(node);
      return { labelColumn: style.gridTemplateColumns.split(" ")[0], padding: style.padding,
        columnGap: style.columnGap, rowGap: style.rowGap };
    }));
    expect(fields).toEqual(fields.map(() => ({ labelColumn: "128px", padding: "9px 10px", columnGap: "8px", rowGap: "4px" })));
    const picker = await job.locator(".icPickerInput").evaluate(node => ({
      height: node.getBoundingClientRect().height, inputSize: getComputedStyle(node.querySelector("input")!).fontSize,
    }));
    expect(picker).toEqual({ height: 34, inputSize: "10px" });

    // The file picker is in the control column at full width, not squeezed under the label.
    const selectorBox = (await job.locator(".programmingSourceSelector").boundingBox())!;
    const fileBox = (await job.locator(".programmingJobImageControl").boundingBox())!;
    expect(Math.abs(fileBox.x - selectorBox.x)).toBeLessThanOrEqual(1);
    expect(fileBox.y).toBeGreaterThan(selectorBox.y + selectorBox.height);
    expect(fileBox.width).toBeGreaterThan(400);
    await expect(job.locator(".programmingJobImageControl > span")).toHaveText("app.bin");
    await page.screenshot({ path: testInfo.outputPath(`pmode-${width}.png`), fullPage: true });
  });
}
