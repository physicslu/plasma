import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, legacyRequests, mockFleet, mockManager, type RunScript } from "./managed-programming-helpers";
import {
  programmingJobAction,
  programmingJobOperation,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";
import { commitProductionSites, programmingJob } from "./production-console-helpers";

// U10: PMode is Manager-managed only. One Facility / one PPU with two Sites
// from the Mock Manager; every Production Batch is one canonical Manager
// Batch. The Factory Console operator contract (Production Set vs next-Batch
// membership, collapse, START snapshot + lock, whole-Batch ABORT, planned IC
// quantity, 1 Hz activity and Batch time) is kept.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;
const ppuLabel = `${ppuId} · PPU ID ${ppuId}`;

async function installFactoryMock(page: Page, script?: (alias: string, siteId: number) => RunScript) {
  return await mockManager(page, { ppus: mockFleet(1, [2]), script });
}

async function commitTwoSiteProductionSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await expect(page.getByRole("region", { name: "LIVE SITE STATUS" }).locator(".factorySiteLedCard")).toHaveCount(2);
}

async function chooseTarget(page: Page) {
  const target = page.getByLabel("Target IC");
  await target.fill("STM32F103C8T6");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
}

async function chooseImage(page: Page) {
  await programmingJob(page).getByLabel("Production Programming Image file").setInputFiles({
    name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });
}

test("Production Set stays visible while the operator changes next-Batch PPU/Site membership", async ({ page }) => {
  await installFactoryMock(page);
  await commitTwoSiteProductionSet(page);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  const facility = live.getByRole("checkbox", { name: `Batch select ${facilityId}`, exact: true });
  const ppu = live.getByRole("checkbox", { name: `Batch select ${ppuLabel}`, exact: true });
  const site1 = live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-01`, exact: true });
  const site2 = live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-02`, exact: true });
  await expect(facility).toBeChecked();
  await expect(ppu).toBeChecked();
  await expect(site1).toBeChecked();
  await expect(site2).toBeChecked();

  await site2.uncheck();
  await expect(page.locator('[data-kpi="production-sites"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="total-ic"] b')).toHaveText("1");
  await expect.poll(() => ppu.evaluate((element: HTMLInputElement) => element.indeterminate)).toBe(true);
  await expect.poll(() => facility.evaluate((element: HTMLInputElement) => element.indeterminate)).toBe(true);
  await expect(live.locator('[data-production-site="2"]')).toHaveAttribute("data-batch-selected", "false");

  await facility.check();
  await expect(site2).toBeChecked();
  await facility.uncheck();
  await expect(site1).not.toBeChecked();
  await expect(site2).not.toBeChecked();
  await facility.check();

  await page.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" }).locator(".operatorPanelBody")).toBeHidden();
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
});

test("Production Programming Job collapse preserves the complete Batch action row", async ({ page }) => {
  await installFactoryMock(page);
  await commitTwoSiteProductionSet(page);

  const job = programmingJob(page);
  await job.getByRole("button", { name: "Collapse Production Programming Job" }).click();
  await expect(job.getByLabel("Target IC")).toBeHidden();
  await expect(programmingJobAction(job, "start")).toBeVisible();
  await expect(programmingJobAction(job, "status")).toBeVisible();
  await expect(programmingJobAction(job, "abort")).toBeVisible();
  await job.getByRole("button", { name: "Expand Production Programming Job" }).click();
  await expect(job.getByLabel("Target IC")).toBeVisible();
});

test("START snapshots Batch membership; running selection is locked and only whole-Batch ABORT is exposed", async ({ page }) => {
  const counters = await installFactoryMock(page, () => ({ runningPolls: 4 }));
  await commitTwoSiteProductionSet(page);
  await chooseTarget(page);

  const job = programmingJob(page);
  await programmingJobOperation(job, "program").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  expect(counters.batches[0].body.targets).toEqual([{ ppu_alias: ppuId, site_ids: [1, 2] }]);
  expect(counters.batches[0].body.icpn).toBe("STM32F103C8T6");
  expect(counters.batches[0].body.operations).toEqual(["erase"]);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live.getByRole("checkbox", { name: `Batch select ${facilityId}`, exact: true })).toBeDisabled();
  await expect(live.getByRole("checkbox", { name: `Batch select ${ppuLabel}`, exact: true })).toBeDisabled();
  await expect(live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-01` })).toBeDisabled();
  await expect(live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-02` })).toBeDisabled();
  await expect(page.getByText("Cancel PPU", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Cancel Site/i)).toHaveCount(0);

  // ABORT while SITE-01 runs: its Job is observed to PASS, the not-yet-submitted
  // SITE-02 is never started (sequential Manager Batch, whole-Batch stop).
  await expect(live.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running");
  await expect(programmingJobAction(job, "abort")).toBeEnabled();
  await programmingJobAction(job, "abort").click();
  await expect(programmingJobStatusValue(job)).toHaveText(/CANCELLED|PARTIAL/, { timeout: 30_000 });
  await expect(live.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  expect(counters.jobs).toHaveLength(1);
  expect(counters.stops).toHaveLength(1);
  expect(counters.mutations.filter(entry => /cancel/i.test(entry))).toEqual([]);
  expect(legacyRequests(counters)).toEqual([]);

  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("100.0%");

  await expect(live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-01` })).toBeEnabled();
  await expect(live.getByRole("checkbox", { name: `Batch select ${ppuLabel} SITE-02` })).toBeEnabled();
});

test("Production Batch exposes planned IC quantity, 1 Hz activity, and Batch time", async ({ page }) => {
  const counters = await installFactoryMock(page, () => ({ runningPolls: 1000 }));
  await commitTwoSiteProductionSet(page);
  await chooseTarget(page);
  await chooseImage(page);

  const job = programmingJob(page);
  await job.getByLabel("Repeat Count").fill("10");
  await expect(page.locator('[data-kpi="total-ic"] b')).toHaveText("20");
  await expect(page.locator('[data-kpi="batch-time"] b')).toHaveText("00:00:00");
  await expect(programmingJobAction(job, "start")).toBeEnabled();
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  expect(counters.batches[0].body.repeat).toBe(10);
  // From here the Manager Batch record is authoritative (the Mock Manager runs
  // one Cycle per Site), so the planned quantity is checked before START only.
  const activeSite = page.locator('[data-production-site="1"]');
  await expect(activeSite).toHaveAttribute("data-site-state", "running");
  const animation = await activeSite.locator(".factorySiteLed i").evaluate(element => {
    const style = getComputedStyle(element);
    return { name: style.animationName, duration: style.animationDuration };
  });
  expect(animation).toEqual({ name: "factoryRunningPulse", duration: "1s" });
  await expect(page.locator('[data-kpi="batch-time"] b')).not.toHaveText("00:00:00", { timeout: 5_000 });

  await programmingJobAction(job, "abort").click();
  await expect.poll(() => counters.stops.length).toBe(1);
});
