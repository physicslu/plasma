import { expect, test, type Page } from "@playwright/test";
import { legacyRequests, mockManager, Z2 } from "./managed-programming-helpers";
import { chooseTestTarget } from "./production-console-helpers";
import {
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
} from "./programming-job-test-helpers";

// U10: Manager-managed only. The Engineering Batch is a Manager Batch
// (POST /api/manager/programming/batches); the PPU-local /api/batches engine
// and the legacy Programming Asset cache are gone. The log observability
// contract is kept: the Image selection, the Batch submission and its result
// are visible in the Engineering Job Log, no cache check is revived, and a
// running Batch exposes only the whole-Batch stop, never a per-Site cancel.

const PPU = { ...Z2, enabledSites: [1, 2], siteCount: 2 };
const IMAGE = Buffer.alloc(1024 * 1024, 0x5a);

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
  await chooseTestTarget(page, "engineering");
}

test("Engineering log records the Manager Batch Programming Image submission without reviving the legacy Asset cache", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [PPU] });
  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");
  const job = programmingJob(page, "engineering");

  await page.getByLabel("Select SITE 1 for programming").check();
  await page.getByLabel("Engineering Programming Image file").setInputFiles({
    name: "observable.bin",
    mimeType: "application/octet-stream",
    buffer: IMAGE,
  });
  await programmingJobOperation(job, "erase").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await programmingJobAction(job, "start").click();

  await expect(log).toContainText("[RESULT] PASS", { timeout: 20_000 });
  expect(counters.batches).toHaveLength(1);
  expect(legacyRequests(counters)).toEqual([]);
  expect(counters.requests.filter(entry => /programming-assets|cache/i.test(entry))).toEqual([]);
  const body = counters.batches[0].body;
  expect(body.operations).toEqual(["program"]);
  expect(Buffer.from(String(body.image_base64), "base64").equals(IMAGE)).toBe(true);

  await expect(log).toContainText("[USR] [IMG] SELECT IMAGE · observable.bin · 1048576 B");
  await expect(log).toContainText("[USR] [START] PROGRAM · PPU z2");
  await expect(log).toContainText(/\[DAT\] \[LOCK\] IMAGE · observable\.bin · 1048576 B · SHA256 [0-9a-f]{64}/);
  await expect(log).toContainText(/\[BAT\] \[BATCH\] [0-9a-f]{32} · 1 Site\(s\)/);
  await expect(log).toContainText("[PPU] [RUN] PASS");
  await expect(log).not.toContainText("CACHE CHECK");
  await expect(log).not.toContainText("CACHE HIT");
});

test("a running Engineering Batch exposes the whole-Batch stop and locks per-Site selection", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [PPU],
    script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS", runningPolls: 4 }),
  });
  await openProgramming(page);
  const job = programmingJob(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  await page.getByLabel("Select SITE 2 for programming").check();
  await programmingJobOperation(job, "program").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await job.getByLabel("Site Retry Limit").fill("3");
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  await expect(programmingJobAction(job, "abort")).toBeEnabled();
  await expect(page.getByLabel("Select SITE 1 for programming")).toBeDisabled();
  await expect(page.getByLabel("Select SITE 2 for programming")).toBeDisabled();

  await programmingJobAction(job, "abort").click();
  await expect.poll(() => counters.stops).toEqual([JSON.stringify({ stop: "STOP_QUEUING" })]);
  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("the running Job is not cancelled");
  await expect(log).toContainText(/\[RESULT\] FAIL · STOP_REQUESTED_/, { timeout: 20_000 });
  await expect(log).toContainText("[SITE RESULT] SITE-01 · FAIL · STOP_REQUESTED_NO_FURTHER_ATTEMPT");
  // No per-Site cancel, abort or PPU-local Batch request ever left the Browser.
  expect(counters.mutations.filter(entry => /cancel|abort/i.test(entry))).toEqual([]);
  expect(legacyRequests(counters)).toEqual([]);
  await expect(programmingJobAction(job, "start")).toBeEnabled();
});
