import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, Z2, legacyRequests, mockManager } from "./managed-programming-helpers";
import {
  expectProgrammingJobContract,
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
  programmingJobPolicy,
} from "./programming-job-test-helpers";

// U10: Manager-managed only (EMode = ManagedProgrammingWorkspace). The
// approved EMode workflow, collapse controls, Target IC binding, the per-Site
// READ and the "only checked Sites" Batch snapshot are kept; every Job is a
// Manager Batch. Mock Manager / Mock PPU at the Browser boundary.

const PPU = { ...Z2, enabledSites: [1, 2], siteCount: 2 };

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
}

async function chooseTarget(page: Page) {
  const job = programmingJob(page, "engineering");
  const target = job.getByPlaceholder("Search ICPN / IC identifier...");
  await target.fill("STM32F103C8T6");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await expect(target).toHaveValue("STM32F103C8T6");
}

test("Engineering Programming renders the approved workflow and binds the Target IC to the Manager Batch", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [PPU] });
  await page.setViewportSize({ width: 1536, height: 1000 });
  await page.goto("/engineering");

  await expect(page.getByRole("heading", { name: "Engineering Mode" })).toBeVisible();
  await expect(page.locator(".engineeringSidebar")).toBeVisible();
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const job = programmingJob(page, "engineering");
  await expectProgrammingJobContract(job);
  await expect(page.getByRole("heading", { name: "SINGLE PPU PROGRAMMING" })).toBeVisible();
  await expect(page.locator(".targetingCard .operatorPanelTitle")).toHaveText(/^1\.\s*SYSTEM SETUP & TARGETING$/);
  await expect(page.getByText("LIVE PROGRESS MONITOR", { exact: true })).toHaveCount(0);
  await expect(page.getByText("TARGET SITES", { exact: true })).toHaveCount(0);
  await expect(page.locator(".liveSiteStatus .operatorPanelTitle")).toHaveText(/^3\.\s*LIVE SITE STATUS/);
  await expect(page.locator(".engineeringProgrammingV2 .recentEvents")).toHaveCount(0);
  await expect(page.getByText("RECENT EVENTS", { exact: true })).toHaveCount(0);
  await expect(programmingJobPolicy(job, "retry")).toHaveValue("0");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Engineering batch read")).toHaveCount(0);
  await expect(job.locator('[data-programming-job-field="operations"] > strong')).toHaveText("2-3. Operations");

  const layout = await page.locator(".engineeringProgrammingV2").evaluate(root => {
    const box = (selector: string) => root.querySelector<HTMLElement>(selector)!.getBoundingClientRect();
    const setup = box(".targetingCard");
    const jobPanel = box(".programmingJobPanel");
    const status = box(".liveSiteStatus");
    return {
      setupTop: setup.top,
      setupBottom: setup.bottom,
      jobTop: jobPanel.top,
      jobBottom: jobPanel.bottom,
      statusTop: status.top,
    };
  });
  expect(layout.setupTop).toBeLessThan(layout.jobTop);
  expect(layout.setupBottom).toBeLessThanOrEqual(layout.jobTop);
  expect(layout.jobBottom).toBeLessThanOrEqual(layout.statusTop);

  await page.getByRole("button", { name: "Collapse System Setup" }).click();
  await expect(page.getByLabel("Engineering Facility")).toBeHidden();
  await expect(page.getByRole("button", { name: "Expand System Setup" })).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Expand System Setup" }).click();
  await expect(page.getByLabel("Engineering Facility")).toBeVisible();

  await page.getByRole("button", { name: "Collapse Engineering Programming Job" }).click();
  await expect(job.getByPlaceholder("Search ICPN / IC identifier...")).toBeHidden();
  await expect(programmingJobAction(job, "start")).toBeVisible();
  await expect(programmingJobAction(job, "status")).toBeVisible();
  await expect(programmingJobAction(job, "abort")).toBeVisible();
  await page.getByRole("button", { name: "Expand Engineering Programming Job" }).click();
  await expect(job.getByPlaceholder("Search ICPN / IC identifier...")).toBeVisible();

  const sidebarWidth = await page.locator(".engineeringSidebar").evaluate(element => element.getBoundingClientRect().width);
  await page.getByRole("button", { name: "Collapse Engineering menu" }).click();
  const collapsedWidth = await page.locator(".engineeringSidebar").evaluate(element => element.getBoundingClientRect().width);
  expect(collapsedWidth).toBeLessThan(sidebarWidth);
  await page.getByRole("button", { name: "Expand Engineering menu" }).click();

  await chooseTarget(page);
  // READ is each qualified Site row's own action.
  await expect(page.getByLabel("Read SITE 1 Flash")).toBeVisible();
  await expect(page.getByLabel("Read SITE 2 Flash")).toBeVisible();

  await page.getByLabel("Select SITE 1 for programming").check();
  await programmingJobOperation(job, "program").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await programmingJobAction(job, "start").click();
  await expect.poll(() => counters.batches.length).toBe(1);
  expect(counters.batches[0].body).toMatchObject({
    icpn: "STM32F103C8T6",
    targets: [{ ppu_alias: "z2", site_ids: [1] }],
    operations: ["erase"],
  });
  expect(legacyRequests(counters)).toEqual([]);

  const siteOne = page.locator(".channelTable tbody tr").filter({ hasText: "SITE-01" });
  await expect(siteOne.locator(".engineeringResult")).toHaveText("PASS", { timeout: 20_000 });
});

test("Read Memory starts an independent single-Site READ Batch, never a programming Batch", async ({ page }) => {
  // No Save File Picker: the verified READ is offered as a Browser download.
  await page.addInitScript(() => { (window as unknown as Record<string, unknown>).showSaveFilePicker = undefined; });
  const counters = await mockManager(page, { ppus: [PPU] });
  await openProgramming(page);
  await chooseTarget(page);

  await page.getByLabel("Read SITE 1 Flash").click();
  await expect(page.getByLabel("SITE 1 Read status")).toHaveText("PASS", { timeout: 20_000 });
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body).toMatchObject({ operation: "read", targets: [{ ppu_alias: "z2", site_ids: [1] }] });
  expect(counters.batches[0].body).not.toHaveProperty("operations");
  expect(legacyRequests(counters)).toEqual([]);
});

test("unselected Sites stay visible and START PROGRAMMING snapshots only checked Sites into one Manager Batch", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [PPU] });
  await openProgramming(page);
  await chooseTarget(page);

  const job = programmingJob(page, "engineering");
  await expectProgrammingJobContract(job);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Select SITE 1 for programming").check();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Select SITE 1 for programming")).toBeChecked();
  await expect(page.getByLabel("Select SITE 2 for programming")).not.toBeChecked();

  await page.getByLabel("Engineering Programming Image file").setInputFiles({ name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });
  // Two Cycles back to back on the same IC (Same-IC Debug): no operator IC
  // replacement pause between them, so the KPIs count Cycles.
  await programmingJobPolicy(job, "replace-ic").uncheck();
  await programmingJobPolicy(job, "repeat").fill("2");
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary.getByText("BATCH SUMMARY", { exact: true })).toBeVisible();
  await expect(summary.locator('[data-kpi="sites"] b')).toHaveText("1");
  await expect(summary.locator('[data-kpi="total-cycles"] b')).toHaveText("2");
  await expect(summary.locator('[data-kpi="cycle-pass-rate"] b')).toHaveText("N/A");
  await expect(summary.locator('[data-kpi="batch-time"] b')).toHaveText("00:00:00");
  // The Mock Manager runs one Cycle per Site: run the snapshot with Repeat 1.
  await programmingJobPolicy(job, "repeat").fill("1");
  await expect(summary.locator('[data-kpi="total-cycles"] b')).toHaveText("1");
  await expect(programmingJobAction(job, "start")).toBeEnabled();
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  expect(counters.batches[0].body).toMatchObject({
    targets: [{ ppu_alias: "z2", site_ids: [1] }],
    operations: ["erase", "program", "verify"],
    repeat: 1,
    replace_ic_before_next_cycle: false,
    retry_limit: 0,
  });
  await expect(summary.locator('[data-kpi="pass"] b')).toHaveText("1", { timeout: 20_000 });
  await expect(summary.locator('[data-kpi="fail"] b')).toHaveText("0");
  // After the run the Summary follows the Manager Batch record (the Mock
  // Manager does not echo the Same-IC flag), so either KPI family may show.
  await expect(summary.locator('[data-kpi="settled-cycles"] b, [data-kpi="processed-ic"] b')).toHaveText("1");
  await expect(summary.locator('[data-kpi="cycle-pass-rate"] b, [data-kpi="yield"] b')).toHaveText("100.0%");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Select SITE 2 for programming")).not.toBeChecked();
});
