import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, mockFleet, mockManager, type Counters, type RunScript } from "./managed-programming-helpers";
import {
  programmingJob as sharedProgrammingJob,
  programmingJobAction,
  programmingJobOperation,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  programmingJob as productionProgrammingJob,
} from "./production-console-helpers";

// U10: Manager-managed only. The global mode-switch execution guard must hold
// while a Manager Batch is non-terminal (running, stopping, or unobservable)
// and release only at a terminal Manager answer. Mock Manager at the Browser
// boundary; `run` is the shared, mutable script of every planned Job, so a
// test decides when the in-flight Job finishes.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function installExecutionApi(page: Page) {
  const run: RunScript = { runningPolls: 100_000 };
  const counters = await mockManager(page, { ppus: mockFleet(1, [2]), script: () => run });
  let failPolls = 0;
  // Manager Batch journal outage: the next N reads answer 503, then the Mock Manager resumes.
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}$/, async route => {
    if (failPolls > 0) {
      failPolls -= 1;
      await route.fulfill({ status: 503, json: { ok: false, error: { code: "manager_unavailable", message: "Manager unavailable" } } });
      return;
    }
    await route.fallback();
  });
  return {
    counters,
    finishJobs() { run.runningPolls = 0; },
    failNextBatchPolls(count: number) { failPolls = count; },
  };
}

function cancels(counters: Counters) {
  return counters.mutations.filter(entry => /cancel|abort/i.test(entry));
}

async function expectModeLocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".globalExecutionGuard")).toContainText("EXECUTION BUSY · 1");
  const before = page.url();
  await link.click({ force: true });
  await expect.poll(() => page.url()).toBe(before);
}

async function expectModeUnlocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).not.toHaveAttribute("aria-disabled", "true", { timeout: 15_000 });
  await expect(page.locator(".globalExecutionGuard")).toHaveCount(0);
}

async function startProductionBatch(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);
  const job = productionProgrammingJob(page);
  await job.getByLabel("Production Programming Image file").setInputFiles({
    name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });
  await expect(programmingJobStatusValue(job)).toHaveText("MANAGER BATCH READY");
  await programmingJobAction(job, "start").click();
  await expectModeLocked(page, "工程模式");
  return job;
}

async function startEngineeringBatch(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  const job = sharedProgrammingJob(page, "engineering");
  await programmingJobOperation(job, "program").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await programmingJobAction(job, "start").click();
  return job;
}

test("Pmod Manager Batch locks Emode through running and stopping until terminal", async ({ page }) => {
  const api = await installExecutionApi(page);
  const job = await startProductionBatch(page);

  await programmingJobAction(job, "abort").click();
  await expect.poll(() => api.counters.stops.length).toBe(1);
  await expect(programmingJobStatusValue(job)).toHaveText(/STOPPING|CANCELLING/);
  await expectModeLocked(page, "工程模式");
  api.finishJobs();
  await expectModeUnlocked(page, "工程模式");
  expect(cancels(api.counters)).toEqual([]);
});

test("successful Pmod Batch releases its execution lease and restores Engineering mode", async ({ page }) => {
  const api = await installExecutionApi(page);
  const job = await startProductionBatch(page);

  api.finishJobs();
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS", { timeout: 15_000 });
  await expectModeUnlocked(page, "工程模式");
});

test("temporary Manager Batch observation failures reconnect and still release the terminal mode guard", async ({ page }) => {
  const api = await installExecutionApi(page);
  const job = await startProductionBatch(page);

  api.failNextBatchPolls(3);
  await expect(programmingJobStatusValue(job)).toHaveText("RECONNECTING");
  await expectModeLocked(page, "工程模式");
  await expect(page.getByLabel("Production batch log")).toContainText("[BAT] OBSERVATION UNAVAILABLE · manager_unavailable: Manager unavailable; nothing was resubmitted");
  api.finishJobs();
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS", { timeout: 15_000 });
  await expectModeUnlocked(page, "工程模式");
  expect(api.counters.batches).toHaveLength(1); // observation never resubmits
});

test("ABORT racing an already finished Batch performs terminal cleanup", async ({ page }) => {
  const api = await installExecutionApi(page);
  const job = await startProductionBatch(page);

  api.finishJobs();
  await programmingJobAction(job, "abort").click();
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS", { timeout: 15_000 });
  await expectModeUnlocked(page, "工程模式");
  expect(api.counters.stops.length).toBeLessThanOrEqual(1);
  expect(api.counters.batches).toHaveLength(1);
});

test("restoring an already successful Batch after reload holds no stale execution lease", async ({ page }) => {
  const api = await installExecutionApi(page);
  const job = await startProductionBatch(page);
  api.finishJobs();
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS", { timeout: 15_000 });

  await page.reload();
  await expect(programmingJobStatusValue(productionProgrammingJob(page))).toHaveText("SUCCESS");
  await expectModeUnlocked(page, "工程模式");
  expect(api.counters.batches).toHaveLength(1);
});

// KNOWN APP BUG (U10, reported, not fixed here): the managed EMode workspace
// (ManagedProgrammingWorkspace) never takes the global Batch execution lease
// (beginBatchExecutionActivity), so a running EMode Manager Batch / READ does
// not lock the PMode navigation. The tests below state the required contract
// and are expected to fail until the app is fixed; then drop `test.fail`.
const EMODE_LEASE_BUG = "managed EMode Batch does not take the global mode-switch execution lease";

test("Emode single-Site READ still locks Pmod until terminal", async ({ page }) => {
  test.fail(true, EMODE_LEASE_BUG);
  const api = await installExecutionApi(page);
  await page.addInitScript(() => { (window as unknown as Record<string, unknown>).showSaveFilePicker = undefined; });
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await chooseTestTarget(page, "engineering");

  await page.getByLabel("Read SITE 1 Flash").click();
  await expectModeLocked(page, "量產模式");
  api.finishJobs();
  await expectModeUnlocked(page, "量產模式");
  expect(cancels(api.counters)).toEqual([]);
});

test("Emode Manager Batch keeps Pmod locked while it runs and releases it at the terminal answer", async ({ page }) => {
  test.fail(true, EMODE_LEASE_BUG);
  const api = await installExecutionApi(page);
  await startEngineeringBatch(page);

  await expectModeLocked(page, "量產模式");
  await expect(page.locator(".channelTable tbody tr").first().locator(".engineeringResult")).toHaveText("—");
  api.finishJobs();
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" }).locator('[data-kpi="pass"] b')).toHaveText("1", { timeout: 15_000 });
  await expectModeUnlocked(page, "量產模式");
  expect(cancels(api.counters)).toEqual([]);
});

test("Emode Manager FAIL terminates the Batch with its exact reason and no Browser Job cancellation", async ({ page }) => {
  const run: RunScript = { outcome: "FAIL", reason: "PPU_COMMUNICATION_TIMEOUT", safeOff: true, runningPolls: 2 };
  const counters = await mockManager(page, { ppus: mockFleet(1, [2]), script: () => run });
  await startEngineeringBatch(page);

  const row = page.locator(".channelTable tbody tr").first();
  await expect(row.locator(".engineeringResult")).toHaveText("FAIL", { timeout: 15_000 });
  await expect(page.getByLabel("Engineering job log")).toContainText("PPU_COMMUNICATION_TIMEOUT");
  await expectModeUnlocked(page, "量產模式");
  expect(cancels(counters)).toEqual([]);
  expect(counters.batches).toHaveLength(1);
});

test("Emode Manager Batch observation outage stays fail-closed until the Manager answers again", async ({ page }) => {
  test.fail(true, EMODE_LEASE_BUG);
  const api = await installExecutionApi(page);
  await startEngineeringBatch(page);

  api.failNextBatchPolls(4);
  await expectModeLocked(page, "量產模式");
  expect(cancels(api.counters)).toEqual([]);

  api.finishJobs();
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" }).locator('[data-kpi="pass"] b')).toHaveText("1", { timeout: 15_000 });
  await expectModeUnlocked(page, "量產模式");
  expect(cancels(api.counters)).toEqual([]);
  expect(api.counters.batches).toHaveLength(1);
});
