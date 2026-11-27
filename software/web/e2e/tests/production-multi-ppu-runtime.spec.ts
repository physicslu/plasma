import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import {
  batchRuns,
  imagePattern,
  managed,
  BATCHES_PATH,
  managerBatch,
  observeManagedTraffic,
  settledManagerBatch,
  type Operation,
} from "./mock-cd-managed-helpers";
import {
  expectProgrammingJobContract,
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";

// U10 PMode on the real Mock CD stack: ONE Manager Batch over two Mock PPUs
// (ppu-a + ppu-b). Console → BFF → Manager ProgrammingBatchCoordinator → each
// PPU's real Bootstrap / Reservation / Job Binding → Mock PPU Runtime.
//
// Serial: an Image-less (Erase-only) Batch never activates a Resource Set, so
// the shared-Image test runs first and makes both PPUs' Resource Sets Active.
test.describe.configure({ mode: "serial" });

const ppus = [managed.ppuA, managed.ppuB];
const sharedImage = imagePattern(4096, 0, 0xa5);
const sharedImageSha = createHash("sha256").update(sharedImage).digest("hex");

function ppuCard(page: Page, alias: string) {
  return page.locator(`[data-production-ppu="${alias}"]`);
}

function siteCard(page: Page, alias: string, siteId = 1) {
  return ppuCard(page, alias).locator(`[data-production-site="${siteId}"]`);
}

function fpsCheckbox(page: Page, alias: string, siteId = 1) {
  return page.getByRole("checkbox", {
    name: `Production Set ${managed.facilityId} ${alias} SITE-${String(siteId).padStart(2, "0")}`,
  });
}

async function openTwoPpuProductionSet(page: Page, operations: Operation[]) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  await expect(page.locator('main[data-programming-backend="manager"]')).toBeVisible();
  await expect(page.locator(".productionTreeFacility").first()).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => document.querySelectorAll("details").forEach(item => { item.open = true; }));
  await expect(page.locator(".productionTreePpu")).toHaveCount(2);

  for (const alias of ppus) {
    await expect(fpsCheckbox(page, alias)).toBeVisible();
    await fpsCheckbox(page, alias).check();
  }
  await page.getByRole("button", { name: "SET PRODUCTION SITES", exact: true }).click();
  for (const alias of ppus) await expect(ppuCard(page, alias)).toBeVisible();
  await expect(page.locator('[data-kpi="production-sites"] b')).toHaveText("2");

  const job = programmingJob(page, "production");
  await job.getByLabel("Target IC").fill(managed.icpn);
  await page.getByRole("option", { name: new RegExp(`^${managed.icpn}(?:\\s|$)`) }).first().click();
  // The Route of the chosen IC supplies the E / P / V operations.
  await expectProgrammingJobContract(job);
  for (const name of ["erase", "program", "verify"] as const) {
    const box = programmingJobOperation(job, name);
    if (operations.includes(name)) await box.check();
    else await box.uncheck();
  }
  if (operations.includes("program") || operations.includes("verify")) {
    await page.getByLabel("Production Programming Image file").setInputFiles({
      name: "production-shared-asset.bin",
      mimeType: "application/octet-stream",
      buffer: sharedImage,
    });
  }
  return job;
}

test("real Production Mock shares one Programming Image across two PPUs for Erase Program Verify in ONE Manager Batch", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  const job = await openTwoPpuProductionSet(page, ["erase", "program", "verify"]);
  await programmingJobAction(job, "start").click();

  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(1);
  const sent = traffic.batches[0];
  expect(sent.body.targets).toEqual(ppus.map(alias => ({ ppu_alias: alias, site_ids: [1] })));
  expect(sent.body.operations).toEqual(["erase", "program", "verify"]);
  expect(sent.body.repeat).toBe(1);
  // The Image is carried once, for both PPUs.
  expect(Buffer.from(String(sent.body.image_base64), "base64").equals(sharedImage)).toBe(true);
  expect(sent.body).not.toHaveProperty("bundle_base64");

  await expect(siteCard(page, managed.ppuA)).toHaveAttribute("data-site-state", "success", { timeout: 60_000 });
  await expect(siteCard(page, managed.ppuB)).toHaveAttribute("data-site-state", "success", { timeout: 60_000 });
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS");
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("100.0%");

  // Manager evidence: one Batch, one Job per PPU with its own Binding, same Image.
  await expect.poll(() => sent.batchId).toMatch(/^[0-9a-f]{32}$/);
  const batch = await settledManagerBatch(request, sent.batchId!);
  expect(batch.outcome).toBe("PASS");
  expect(batch.units.map(unit => unit.ppu_alias)).toEqual(ppus);
  const runs = await batchRuns(request, batch);
  expect(runs.map(item => item.unit.ppu_alias)).toEqual(ppus);
  expect(new Set(runs.map(item => item.attempt.job_id)).size).toBe(2);
  expect(new Set(runs.map(item => item.attempt.job_binding_sha256)).size).toBe(2);
  for (const { run } of runs) {
    expect(run.outcome).toBe("PASS");
    expect(run.receipt?.expected_image_sha256).toBe(sharedImageSha);
    expect(run.receipt?.observed_operations).toEqual(["erase", "program", "verify"]);
  }
  for (const alias of ppus) {
    const activation = batch.resource_activation?.[alias];
    if (activation) expect(activation.result).toBe("PASS");
  }
  expect(traffic.legacy).toEqual([]);
});

test("real Production Mock submits one Manager Batch for two PPUs (Erase) and completes both", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  const job = await openTwoPpuProductionSet(page, ["erase"]);
  await programmingJobAction(job, "start").click();

  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(1);
  const sent = traffic.batches[0];
  expect(sent.body.targets).toEqual(ppus.map(alias => ({ ppu_alias: alias, site_ids: [1] })));
  expect(sent.body.operations).toEqual(["erase"]);
  // Erase only: no Image, the Route's whole Flash range.
  expect(sent.body).not.toHaveProperty("image_base64");
  expect(sent.body).toMatchObject({ address: managed.flashBase, length: managed.flashSize });

  for (const alias of ppus) {
    await expect.poll(async () => siteCard(page, alias).getAttribute("data-site-state"), { timeout: 15_000 })
      .toMatch(/^(running|success)$/);
  }
  await expect(siteCard(page, managed.ppuA)).toHaveAttribute("data-site-state", "success", { timeout: 60_000 });
  await expect(siteCard(page, managed.ppuB)).toHaveAttribute("data-site-state", "success", { timeout: 60_000 });
  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS");
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");

  await expect.poll(() => sent.batchId).toMatch(/^[0-9a-f]{32}$/);
  const batch = await settledManagerBatch(request, sent.batchId!);
  expect(batch.outcome).toBe("PASS");
  // Both PPUs were already Active: an Erase-only Batch never runs B1/B2/B3.
  expect(batch.resource_activation ?? {}).toEqual({});
  const runs = await batchRuns(request, batch);
  expect(runs.map(item => [item.unit.ppu_alias, item.run.outcome])).toEqual(ppus.map(alias => [alias, "PASS"]));
  expect(traffic.legacy).toEqual([]);
});

test("real Production Mock ABORT is whole-Batch STOP QUEUING: started Jobs complete normally, nothing new is submitted", async ({ page, request }) => {
  // KNOWN PRE-EXISTING, INTERMITTENT APP BUG (BFF, unchanged by U10): the
  // canonical Batch stop relay first GETs the Batch from the Manager
  // (authorizedAliases → managerProgrammingRead) and then POSTs .../stop in the
  // same Worker request. Against the HTTP/1.0 Manager that POST intermittently
  // fails in the Vinext/workerd runtime with "Network connection lost"
  // (retryable), the BFF answers 503 manager_unavailable, the Console logs
  // "[BAT] ABORT ERROR" and the Batch runs every queued Cycle. This test stays
  // strict (no test.fail): it is the product acceptance for STOP QUEUING.
  const traffic = observeManagedTraffic(page);
  const repeat = 50;
  const job = await openTwoPpuProductionSet(page, ["erase", "program", "verify"]);
  // Same-IC Debug: every Cycle continues by itself, so queued work exists to stop.
  await job.getByLabel("Repeat Count").fill(String(repeat));
  await job.getByLabel("Replace IC before next Cycle").uncheck();
  await programmingJobAction(job, "start").click();

  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(1);
  const sent = traffic.batches[0];
  expect(sent.body.repeat).toBe(repeat);
  expect(sent.body.replace_ic_before_next_cycle).toBe(false);
  await expect.poll(() => sent.batchId, { timeout: 15_000 }).toMatch(/^[0-9a-f]{32}$/);
  try {
    // Wait until both PPU lanes are running in the Console.
    for (const alias of ppus) {
      await expect(siteCard(page, alias)).toHaveAttribute("data-site-state", "running", { timeout: 30_000 });
    }

    // Only the whole-Batch stop exists; no per-PPU cancel.
    await expect(page.getByRole("button", { name: "Cancel PPU", exact: true })).toHaveCount(0);
    const [stopResponse] = await Promise.all([
      page.waitForResponse(response => response.request().method() === "POST"
        && new URL(response.url()).pathname === `${BATCHES_PATH}/${sent.batchId}/stop`),
      programmingJobAction(job, "abort").click(),
    ]);
    expect(traffic.stops).toEqual([sent.batchId]);
    // The Manager accepted STOP QUEUING (the known bug fails here with 503).
    expect(stopResponse.status(), await stopResponse.text()).toBe(200);
    await expect(page.getByLabel("Production batch log")).not.toContainText("ABORT ERROR");

    const batch = await settledManagerBatch(request, sent.batchId!, 90_000);
    expect(batch.stop_requested).toBe(true);
    expect(batch.outcome).not.toBe("PASS");
    expect(String((batch as unknown as { reason: string }).reason)).toMatch(/^STOP_REQUESTED/);
    const cycles = (batch as unknown as {
      cycles: { planned: number; settled: number; pass: number; fail: number; remaining: number };
    }).cycles;
    expect(cycles.planned).toBe(repeat * ppus.length);
    // Every Job that had been started finished normally (PASS), none was cancelled.
    expect(cycles.settled).toBeGreaterThanOrEqual(ppus.length);
    expect(cycles.pass).toBe(cycles.settled);
    expect(cycles.fail).toBe(0);
    for (const unit of batch.units) {
      for (const attempt of unit.attempts) expect(attempt.outcome).toBe("PASS");
    }
    // Queued Cycles were never submitted, and nothing is submitted after the stop.
    expect(cycles.remaining).toBeGreaterThan(0);
    expect(cycles.settled).toBeLessThan(cycles.planned);
    const settledAttempts = batch.counts.attempts;
    await page.waitForTimeout(2_000);
    expect((await managerBatch(request, sent.batchId!)).counts.attempts).toBe(settledAttempts);

    await expect(programmingJobStatusValue(job)).not.toHaveText(/RUNNING|STOPPING/, { timeout: 30_000 });
    for (const alias of ppus) {
      await expect(siteCard(page, alias)).not.toHaveAttribute("data-site-state", /running|faulted|error/, { timeout: 30_000 });
    }
    expect(traffic.batches).toHaveLength(1);
    expect(traffic.legacy).toEqual([]);
  } finally {
    // Never leave a Batch running for the next spec, whatever failed above.
    await settledManagerBatch(request, sent.batchId!, 120_000);
  }
});
