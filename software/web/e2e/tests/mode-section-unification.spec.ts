import { expect, test, type Locator, type Page } from "@playwright/test";
import { FIRMWARE, Z2, mockManager } from "./managed-programming-helpers";

// Host-only Console acceptance of the unified EMode / PMode chapter structure
// (1 SYSTEM SETUP & TARGETING · 2 PROGRAMMING JOB with 2-1 … 2-4 · 3 LIVE SITE
// STATUS · 4 LOG) and of the removal of the duplicated result UI. Mock Manager
// at the Browser boundary: NOT physical PPU, FPGA or DUT evidence.

const FIELDS: Array<[string, string]> = [
  ["target", "Target IC"],
  ["image", "Programming Source"],
  ["operations", "Operations"],
  ["policy", "Batch Policy"],
];

/** Every numbered chapter title of one mode, in page order: "<n>. <title>". */
function chapters(scope: Locator): Promise<string[]> {
  // Batch Summary shares the panel header but is not a numbered chapter.
  return scope.locator(".operatorPanelTitle").evaluateAll(nodes => nodes
    .map(node => ({
      number: node.querySelector("span")?.textContent?.trim() ?? "",
      title: node.querySelector("strong")?.textContent?.trim() ?? "",
    }))
    .filter(item => /^\d+\.$/.test(item.number))
    .map(item => `${item.number} ${item.title}`));
}

/**
 * Numbered chapter header presentation, for the cross-mode comparison. The
 * rendered height follows the mode's own meta line (PMode carries a workflow
 * chip), so the contract is the header box and the title typography.
 */
function headerMetrics(scope: Locator) {
  return scope.locator(".operatorPanelTitle").evaluateAll(nodes => nodes
    .filter(node => /^\d+\.$/.test(node.querySelector("span")?.textContent?.trim() ?? ""))
    .map(node => {
      const title = getComputedStyle(node.querySelector("strong")!);
      const number = getComputedStyle(node.querySelector("span")!);
      const header = getComputedStyle(node.closest("header")!);
      return {
        size: title.fontSize,
        weight: title.fontWeight,
        numberSize: number.fontSize,
        numberWeight: number.fontWeight,
        minHeight: header.minHeight,
        padding: header.padding,
        borderBottom: header.borderBottomWidth,
      };
    }));
}

async function expectJobFieldNumbering(job: Locator) {
  for (const [index, [field, label]] of FIELDS.entries()) {
    await expect(job.locator(`[data-programming-job-field="${field}"] > strong`)).toHaveText(`2-${index + 1}. ${label}`);
  }
  // No bare "1." … "4." sub-item is left in either mode.
  await expect(job.getByText(/^[1-4]\.\s/)).toHaveCount(0);
}

/** Labels keep the shared Operator typography, one line each, never clipped. */
async function expectLabelMetrics(job: Locator) {
  const labels = await job.locator(".programmingJobField > strong").evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node);
    return { size: style.fontSize, weight: style.fontWeight, clipped: node.scrollWidth > node.clientWidth };
  }));
  expect(labels).toHaveLength(4);
  expect(labels).toEqual(labels.map(() => ({ size: "11px", weight: "800", clipped: false })));
  const labelLeft = await job.locator(".programmingJobField > strong")
    .evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().left)));
  expect(new Set(labelLeft).size).toBe(1);
}

async function expectNoHorizontalOverflow(page: Page, scope: Locator) {
  expect(await scope.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

async function openEmode(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: /Programming|燒錄/ }).first().click();
  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE");
  return workspace;
}

async function openPmode(page: Page) {
  await page.goto("/fleet");
  const factory = page.locator('main[data-programming-backend="manager"]');
  await expect(factory).toBeVisible();
  await expect(page.locator(".productionTreeFacility").first()).toBeVisible();
  await page.evaluate(() => document.querySelectorAll("details").forEach(item => { item.open = true; }));
  return factory;
}

test("EMode has the four chapters, 2-1 … 2-4, and no duplicated result UI", async ({ page }, testInfo) => {
  await mockManager(page);
  const workspace = await openEmode(page);

  expect(await chapters(workspace)).toEqual([
    "1. SYSTEM SETUP & TARGETING",
    "2. PROGRAMMING JOB",
    "3. LIVE SITE STATUS",
    "4. ENGINEERING JOB LOG",
  ]);
  const job = page.getByRole("region", { name: "Engineering Programming Job" });
  await expectJobFieldNumbering(job);
  await expectLabelMetrics(job);

  await job.getByPlaceholder("Search ICPN / IC identifier...").fill("STM32F103");
  await job.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await workspace.getByLabel("Select SITE 2 for programming").check();
  await job.getByLabel("Engineering Programming Image file").setInputFiles(
    { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });

  // The cleanup removes nothing operational: E / P / V, per-Site READ, the
  // Bundle source, Retry / Stop Policy and the Batch Status all stay.
  for (const name of ["erase", "program", "verify"]) {
    await expect(job.getByLabel(`Engineering operation ${name}`)).toBeChecked();
  }
  const live = workspace.getByRole("region", { name: "Engineering Site selection" });
  await expect(live.getByRole("button", { name: /^Read SITE \d+ Flash$/ })).toHaveCount(1);
  await expect(job.getByRole("radio", { name: "Bundle", exact: true })).toBeVisible();
  await expect(job.getByLabel("Site Retry Limit")).toBeEnabled();
  await expect(job.getByLabel("Engineering Stop Policy")).toBeEnabled();
  await expect(job.getByRole("status", { name: "BATCH STATUS" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("emode-1680-ready.png"), fullPage: true });

  await job.getByRole("button", { name: /START PROGRAMMING/ }).click();
  const log = workspace.getByLabel("Engineering job log");
  await expect(log).toContainText("[RUN] PASS ·", { timeout: 20_000 });

  // The duplicated engineering result UI is gone; the Log holds the record.
  await expect(workspace.getByTestId("batch-attempts")).toHaveCount(0);
  await expect(workspace.getByText("BATCH ATTEMPTS")).toHaveCount(0);
  await expect(workspace.getByLabel("Programming run", { exact: true })).toHaveCount(0);
  await expect(workspace.getByLabel("Programming receipt")).toHaveCount(0);
  await expect(workspace.locator(".programmingRunView")).toHaveCount(0);
  await expect(workspace.getByTestId("run-outcome")).toHaveCount(0);
  await expect(log).toContainText(/Run \S+ · Job \S+/);
  await expect(log).toContainText("SAFE_OFF VERIFIED");
  await expect(workspace).not.toContainText("observed_steps");
  // The Site row still carries the Batch verdict.
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("PASS");
  await page.screenshot({ path: testInfo.outputPath("emode-1680-pass.png"), fullPage: true });

  await page.setViewportSize({ width: 820, height: 900 });
  await expect(job.locator('[data-programming-job-field="policy"] > strong')).toBeVisible();
  await expectLabelMetrics(job);
  await expectNoHorizontalOverflow(page, job);
  await page.screenshot({ path: testInfo.outputPath("emode-820-pass.png"), fullPage: true });
});

for (const width of [1680, 820]) {
  test(`PMode has the same four chapters and 2-1 … 2-4 at ${width}px, with no Receipts panel`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockManager(page, { ppus: [Z2] });
    const factory = await openPmode(page);
    await page.getByLabel("Production Set lab z2 SITE-02").check();
    await page.getByRole("button", { name: "SET PRODUCTION SITES" }).click();

    expect(await chapters(factory)).toEqual([
      "1. SYSTEM SETUP & TARGETING",
      "2. PROGRAMMING JOB",
      "3. LIVE SITE STATUS",
      "4. FACTORY LOG",
    ]);
    // PMode keeps its own Site presentation and its domain name in the meta line.
    await expect(page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" })).toContainText("PRODUCTION SITE SELECTION");
    await expect(page.locator(".productionTree")).toBeVisible();

    const job = page.getByRole("region", { name: "Production Programming Job" });
    await job.getByLabel("Target IC").fill("STM32F103");
    await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
    await job.getByLabel("Production Programming Image file").setInputFiles(
      { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });
    await expectJobFieldNumbering(job);
    await expectLabelMetrics(job);

    // PMode semantics are untouched: one Flash Cycle Operation, Retry disabled.
    const operations = job.locator("[data-programming-job-operation]");
    await expect(operations).toHaveCount(1);
    await expect(operations).toHaveAttribute("data-programming-job-operation", "flash_cycle");
    await expect(job.getByLabel("Site Retry Limit")).toBeDisabled();

    // Field metrics stay the shared PMode values (no EMode label column leak).
    const fields = await job.locator(".programmingJobField").evaluateAll(nodes => nodes.map(node => {
      const style = getComputedStyle(node);
      return { padding: style.padding, columnGap: style.columnGap, rowGap: style.rowGap };
    }));
    expect(fields).toEqual(fields.map(() => ({ padding: "9px 10px", columnGap: "10px", rowGap: "4px" })));

    // No RECEIPTS & DIAGNOSTICS panel, before or after a batch.
    await expect(page.getByText("RECEIPTS & DIAGNOSTICS")).toHaveCount(0);
    await expect(page.locator("[data-receipt-site]")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`pmode-${width}-ready.png`), fullPage: true });

    await job.getByRole("button", { name: /START PROGRAMMING/ }).click();
    await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/SUCCESS|PARTIAL|ERROR/, { timeout: 30_000 });
    await expect(page.getByText("RECEIPTS & DIAGNOSTICS")).toHaveCount(0);
    await expect(page.locator("[data-receipt-site]")).toHaveCount(0);
    await expect(page.locator(".programmingRunView")).toHaveCount(0);
    // The Factory Log is the single operation record, and it stays traceable.
    const log = page.getByLabel("Production batch log");
    await expect(log).toContainText(/\[RUN\] PASS · Run \S+ · Job \S+/);
    await expect(log).toContainText("SAFE_OFF VERIFIED");
    await expect(page.getByRole("button", { name: "Download .log" })).toBeEnabled();
    await expect(page.locator("main")).not.toContainText("observed_steps");
    await expectNoHorizontalOverflow(page, job);
    await page.screenshot({ path: testInfo.outputPath(`pmode-${width}-done.png`), fullPage: true });
  });
}

test("both modes render the chapter titles with the same typography and header height", async ({ page }) => {
  await mockManager(page, { ppus: [Z2] });
  const factory = await openPmode(page);
  const pmode = await headerMetrics(factory);
  const pmodeTitles = await chapters(factory);

  const workspace = await openEmode(page);
  const emode = await headerMetrics(workspace);
  const emodeTitles = await chapters(workspace);

  expect(pmode).toHaveLength(4);
  expect(emode).toHaveLength(4);
  const sample = pmode[0];
  expect(sample).toMatchObject({ size: "11px", weight: "900", minHeight: "30px", padding: "5px 8px" });
  // Same title typography, same header box, in every chapter of both modes.
  expect([...pmode, ...emode]).toEqual([...pmode, ...emode].map(() => sample));
  // Same chapter order; only the Log carries the mode's own name.
  expect(emodeTitles.slice(0, 3)).toEqual(pmodeTitles.slice(0, 3));
  expect(emodeTitles[3]).toBe("4. ENGINEERING JOB LOG");
  expect(pmodeTitles[3]).toBe("4. FACTORY LOG");
});
