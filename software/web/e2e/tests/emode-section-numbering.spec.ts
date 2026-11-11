import { expect, test } from "@playwright/test";
import { FIRMWARE, mockManager } from "./managed-programming-helpers";

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

  // Label column and controls share one grid; every control has the same height.
  const labelLeft = await job.locator(".programmingJobField > strong")
    .evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().left)));
  expect(new Set(labelLeft).size).toBe(1);
  const heights = await job.locator(".icPickerInput, .programmingSourceSelector, .programmingJobImageControl, .programmingJobPolicyControls input, .programmingJobPolicyControls select")
    .evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().height)));
  expect(new Set(heights).size, `control heights ${heights.join(", ")}`).toBe(1);

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
  await page.screenshot({ path: testInfo.outputPath("emode-numbered-ready.png"), fullPage: true });

  await job.getByRole("button", { name: /START PROGRAMMING/ }).click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByTestId("batch-attempts")).toBeVisible();
  await expect(workspace.getByLabel("Programming run", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("emode-numbered-pass.png"), fullPage: true });

  // Narrow container: the 2-N fields stack without horizontal overflow.
  await page.setViewportSize({ width: 820, height: 900 });
  await expect(job.locator('[data-programming-job-field="policy"] > strong')).toBeVisible();
  expect(await job.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("emode-numbered-narrow.png"), fullPage: true });
});
