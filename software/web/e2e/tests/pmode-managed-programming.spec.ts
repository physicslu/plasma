import { expect, test, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, RESOURCE_SHA, Z2, legacyRequests, mockManager, sha,
  type Counters, type MockPpu, type RunScript,
} from "./managed-programming-helpers";

// Host-only Console acceptance of PMode → Factory Console on the formal
// Manager backend. Mock Manager / Mock PPUs / Fake Provider at the Browser
// boundary. These results are NOT multi-PPU or multi-Site physical evidence
// and never count as production qualification.

const LINE2: MockPpu = { alias: "line2", ppuId: "line2-01", facilityId: "lab", enabledSites: [2] };
const imageFile = { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE };
const bundleFile = { name: "customer-release.zip", mimeType: "application/zip", buffer: BUNDLE };

async function openFactory(page: Page) {
  await page.goto("/fleet");
  const factory = page.locator('main[data-programming-backend="manager"]');
  await expect(factory).toBeVisible();
  await expect(page.locator(".productionTreeFacility").first()).toBeVisible();
  await page.evaluate(() => document.querySelectorAll("details").forEach(item => { item.open = true; }));
  return factory;
}

async function prepare(page: Page, selection: Array<[string, number[]]>, source: "image" | "bundle" | null = "image") {
  const factory = await openFactory(page);
  for (const [alias, siteIds] of selection) {
    for (const siteId of siteIds) await page.getByLabel(`Production Set lab ${alias} SITE-0${siteId}`).check();
  }
  await page.getByRole("button", { name: "SET PRODUCTION SITES" }).click();
  const job = page.getByRole("region", { name: "Production Programming Job" });
  await job.getByLabel("Target IC").fill("STM32F103");
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
  if (source === "bundle") {
    await job.getByRole("radio", { name: "Bundle", exact: true }).click();
    await job.getByLabel("Production Programming Bundle file").setInputFiles(bundleFile);
  } else if (source === "image") {
    await job.getByLabel("Production Programming Image file").setInputFiles(imageFile);
  }
  return { factory, job, start: job.getByRole("button", { name: /START PROGRAMMING/ }) };
}

const site = (page: Page, alias: string, siteId: number) =>
  page.locator(`[data-production-ppu="${alias}"] [data-production-site="${siteId}"]`);
const summary = (page: Page) => page.getByRole("region", { name: "Production Batch Summary" });
// The FACTORY LOG is the only on-screen operation record in PMode: the
// RECEIPTS & DIAGNOSTICS panel and its per-Site run views were removed.
const factoryLog = (page: Page) => page.getByLabel("Production batch log");
const writes = (counters: Counters) => counters.mutations.filter(entry => !entry.endsWith("/api/manager/ppu"));

async function finished(page: Page) {
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/SUCCESS|PARTIAL|ERROR|CANCELLED/, { timeout: 30_000 });
}


test("PMode topology remains Manager Registry/Fleet and never calls the Mock programming endpoint", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2,
    { alias: "spare", ppuId: "spare-01", lifecycle: "pending" }] });
  await openFactory(page);
  await expect(page.getByLabel("Factory communication health")).toContainText("Gateway ONLINE");
  await expect(page.locator(".productionTreePpu")).toHaveCount(2);
  expect(legacyRequests(counters)).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("one Manager Start and ONE canonical Batch serves two PPUs with separate Job/Binding identities", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2] });
  const { job, start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await expect(job.getByLabel("Repeat Count")).toBeEnabled();
  await expect(job.getByLabel("Repeat Count")).toHaveValue("1");
  await expect(job.getByLabel("Replace IC before next Cycle")).toBeChecked();
  await expect(start).toBeEnabled();
  await start.dblclick();
  await finished(page);
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body.targets).toEqual([
    { ppu_alias: "z2", site_ids: [2] }, { ppu_alias: "line2", site_ids: [2] },
  ]);
  expect(counters.batches[0].body.operations).toEqual(["erase", "program", "verify"]);
  expect(counters.batches[0].body.repeat).toBe(1);
  expect(counters.starts.map(item => item.alias)).toEqual(["z2", "line2"]);
  expect(new Set(counters.starts.map(item => item.body.plan_id)).size).toBe(2);
  expect(new Set(counters.jobs).size).toBe(2);
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(summary(page)).toContainText("100.0%");
  await expect(factoryLog(page)).toContainText("[EVIDENCE] Site interface: openocd");
  expect(legacyRequests(counters)).toEqual([]);
  await expect(page.locator("[data-receipt-site]")).toHaveCount(0);
});

test("Site PASS/FAIL is per-Unit, not inferred from Batch HTTP 200; yield counts once", async ({ page }) => {
  const script = (_alias: string, siteId: number): RunScript =>
    siteId === 2 ? { outcome: "FAIL", reason: "READBACK_SHA256_MISMATCH", safeOff: true } : {};
  const counters = await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2] }], script });
  const { job, start } = await prepare(page, [["z2", [1, 2]]]);
  await job.getByLabel("Site Retry Limit").fill("0");
  await start.click();
  await finished(page);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "faulted");
  await expect(summary(page)).toContainText("50.0%");
  expect(counters.batches).toHaveLength(1);
  expect(counters.starts).toHaveLength(2);
  await expect(factoryLog(page)).toContainText("READBACK_SHA256_MISMATCH");
});

test("UNKNOWN latches its PPU but another PPU can complete; no blind repeat", async ({ page }) => {
  const script = (alias: string, siteId: number): RunScript => alias === "z2" && siteId === 1
    ? { outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT" } : {};
  const counters = await mockManager(page, {
    ppus: [{ ...Z2, enabledSites: [1, 2] }, LINE2], script,
  });
  const { job, start } = await prepare(page, [["z2", [1, 2]], ["line2", [2]]]);
  await job.getByLabel("Site Retry Limit").fill("0");
  await start.click();
  await finished(page);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "error");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "stopped");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "success");
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.starts.map(item => item.alias)).toEqual(["z2", "line2"]);
  await expect(page.getByTestId("managed-readiness")).toContainText("START RECONCILIATION REQUIRED");
});

test("offline or interface-incompatible PPU fails closed before Manager Start", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, { ...LINE2, transport: "unreachable" }] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await expect(page.getByTestId("managed-readiness")).toContainText("PPU OFFLINE");
  await expect(start).toBeDisabled();
  expect(counters.issued).toHaveLength(0);
  expect(counters.batches).toHaveLength(0);
});

test("mixed OpenOCD and Mock interfaces require a matching Profile; never fabricate HIL success", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, { ...LINE2, siteInterface: "mock" }] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await expect(page.getByTestId("managed-readiness")).toContainText("PROGRAMMING UNAVAILABLE");
  await expect(start).toBeDisabled();
  expect(counters.batches).toHaveLength(0);
});

test("native Manager Retry is bounded 0..5 and only a definite FAIL can retry", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", safeOff: true }) });
  const { job, start } = await prepare(page, [["z2", [2]]]);
  const retry = job.getByLabel("Site Retry Limit");
  await expect(retry).toBeEnabled();
  await retry.fill("6");
  await expect(start).toBeDisabled();
  await retry.fill("1");
  await expect(start).toBeEnabled();
  await start.click();
  await finished(page);
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body.retry_limit).toBe(1);
  expect(counters.starts).toHaveLength(2);
});

test("Stop Policy is enforced by Manager, and does not resubmit later Sites", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [{ ...Z2, enabledSites: [1, 2] }, LINE2],
    script: () => ({ outcome: "FAIL", safeOff: true }),
  });
  const { job, start } = await prepare(page, [["z2", [1, 2]], ["line2", [2]]]);
  await job.getByLabel("Site Retry Limit").fill("0");
  await job.getByLabel("Stop Policy").selectOption("1");
  await start.click();
  await finished(page);
  expect(counters.batches[0].body.stop_policy).toEqual({ kind: "failed_sites", threshold: 1 });
  expect(counters.starts).toHaveLength(1);
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "stopped");
});

test("ABORT uses canonical Manager Stop API; in-flight Job completes without resubmission", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [Z2, LINE2], script: () => ({ runningPolls: 6 }),
  });
  const { job, start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await start.click();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  await job.getByRole("button", { name: "ABORT" }).click();
  await finished(page);
  expect(counters.stops).toHaveLength(1);
  expect(counters.starts.map(item => item.alias)).toEqual(["z2"]);
});

test("switching Image to Bundle clears source and never submits by itself", async ({ page }) => {
  const counters = await mockManager(page);
  const { job, start } = await prepare(page, [["z2", [2]]]);
  await expect(start).toBeEnabled();
  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await expect(page.getByTestId("managed-readiness")).toContainText("BUNDLE REQUIRED");
  await expect(start).toBeDisabled();
  expect(counters.issued).toHaveLength(0);
  expect(counters.batches).toHaveLength(0);
});

test("Bundle goes unchanged in one canonical multi-PPU request", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]], "bundle");
  await start.click();
  await finished(page);
  expect(counters.batches).toHaveLength(1);
  expect(Buffer.from(String(counters.batches[0].body.bundle_base64), "base64").equals(BUNDLE)).toBe(true);
  expect(counters.batches[0].body).not.toHaveProperty("image_base64");
});

test("definite 4xx refusal does not start a Site and does not pretend success", async ({ page }) => {
  const counters = await mockManager(page, {
    batchStatus: 422, batchError: { code: "bundle_resource_not_qualified", message: "Resource Set mismatch" },
  });
  const { start } = await prepare(page, [["z2", [2]]]);
  await start.click();
  await expect(factoryLog(page)).toContainText("Resource Set mismatch");
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(0);
});

test("browser reload observes the SAME durable Manager Batch, never queues new Jobs", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [Z2, LINE2], script: () => ({ runningPolls: 8 }),
  });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await start.click();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  await page.reload();
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/RUNNING|SUCCESS/, { timeout: 20_000 });
  expect(counters.batches).toHaveLength(1);
  expect(counters.issued).toHaveLength(1);
  await finished(page);
  const reads = counters.requests.filter(item => item.startsWith("GET /api/manager/programming/batches/"));
  expect(reads.length).toBeLessThan(25); // One bounded observer, no topology/effect feedback loop.
  expect(counters.starts).toHaveLength(2);
});

test("UNKNOWN appearing after reload retains a Start hold after terminal Batch cleanup", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [Z2, LINE2],
    script: (alias) => alias === "z2"
      ? { outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT", runningPolls: 4 }
      : { runningPolls: 4 },
  });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await start.click();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  await page.reload();
  await expect(page.getByTestId("managed-readiness"))
    .toContainText("START RECONCILIATION REQUIRED", { timeout: 20_000 });
  await page.reload();
  await expect(page.getByTestId("managed-readiness"))
    .toContainText("START RECONCILIATION REQUIRED", { timeout: 20_000 });
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
});

test("lost Batch POST response is held by Start ID and read-only reconciled, never resent", async ({ page }) => {
  const counters = await mockManager(page, { batchLost: true });
  const { start } = await prepare(page, [["z2", [2]]]);
  await start.click();
  await expect(page.getByTestId("managed-readiness")).toContainText("START RECONCILIATION REQUIRED");
  expect(counters.batches).toHaveLength(1);
  await page.reload();
  await expect.poll(() => counters.reconciles.length).toBeGreaterThan(0);
  expect(counters.batches).toHaveLength(1);
  expect(counters.issued).toHaveLength(1);
});

test("Erase-only is one Manager programming Job with an explicit Route flash range and no Image", async ({ page }) => {
  const counters = await mockManager(page);
  const { job } = await prepare(page, [["z2", [2]]], null);
  await job.locator('[data-programming-job-operation="program"]').uncheck();
  await job.locator('[data-programming-job-operation="verify"]').uncheck();
  const start = job.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(start).toBeEnabled();
  await start.click();
  await finished(page);
  expect(counters.batches[0].body.operations).toEqual(["erase"]);
  expect(counters.batches[0].body).not.toHaveProperty("image_base64");
  expect(counters.batches[0].body.address).toBe(0x08000000);
  expect(counters.batches[0].body.length).toBe(65536);
});

// A journal outage must not hide or release an already admitted write, even
// though reload clears the IC/source controls. Reconciliation is GET-only.
for (const retainStart of [true, false]) {
 test(`unreadable persisted Batch with ${retainStart ? "immutable Start" : "only the older Batch ID"} stays held before IC selection and submits nothing`, async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ runningPolls: 6 }) });
  const { start } = await prepare(page, [["z2", [2]]]);
  await start.click();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  const held = await page.evaluate(() => sessionStorage.getItem("plasma-managed-production-start-v1"));
  expect(held).toMatch(/^[0-9a-f]{32}$/);
  if (!retainStart) await page.evaluate(() => sessionStorage.removeItem("plasma-managed-production-start-v1"));
  await page.route("**/api/manager/programming/batches/*", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ error: { message: "Journal unavailable" } }),
  }));
  await page.reload();
  await expect(page.getByTestId("managed-readiness")).toContainText(retainStart ? "START RECONCILIATION REQUIRED" : "BATCH OBSERVATION REQUIRED");
  await expect(page.getByRole("region", { name: "Production Programming Job" }).getByLabel("Target IC")).toHaveValue("");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
  expect(await page.evaluate(() => sessionStorage.getItem("plasma-managed-production-start-v1"))).toBe(retainStart ? held : null);
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  await page.unroute("**/api/manager/programming/batches/*");
  if (retainStart) await page.getByRole("button", { name: "RECONCILE MANAGER START" }).click();
  else await page.reload();
  await finished(page);
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
});
}

test("a journal response for a different Start cannot replace the immutable reload hold", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ runningPolls: 6 }) });
  const { start } = await prepare(page, [["z2", [2]]]);
  const accepted = page.waitForResponse(response => response.request().method() === "POST"
    && response.url().endsWith("/api/manager/programming/batches"));
  await start.click();
  const { batch } = await (await accepted).json();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  await page.route("**/api/manager/programming/batches/*", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ ok: true, batch: { ...batch, start_id: "f".repeat(32) } }),
  }));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Retained for read-only reconciliation; no resubmission");
  await expect(page.getByTestId("managed-readiness")).toContainText("START RECONCILIATION REQUIRED");
  expect(await page.evaluate(() => sessionStorage.getItem("plasma-managed-production-start-v1"))).toBe(batch.start_id);
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
});


test("concurrent Site lanes: every Site gets its own Manager run receipt and one evidence line", async ({ page }) => {
  // WP-07: with max_concurrent_jobs 2 the Manager runs both Sites at once and
  // the Batch carries only the most recently submitted run as current_run.
  const counters = await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2] }], concurrentLanes: true });
  const { job, start } = await prepare(page, [["z2", [1, 2]]]);
  await job.getByLabel("Site Retry Limit").fill("0");
  await start.click();
  await finished(page);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "success");
  const log = factoryLog(page);
  for (const siteId of [1, 2]) {
    const label = `PPU z2 · PPU ID z2-hil · SITE-0${siteId}`;
    await expect(log).toContainText(new RegExp(`\\[RUN\\] PASS · Run [0-9a-f]{32} · Job \\S+ · SAFE_OFF VERIFIED.* · ${label}`));
    await expect(log).toContainText(new RegExp(`\\[RECEIPT\\] Job \\S+ · Operations .* · ${label}`));
    await expect(log).toContainText(`[SITE] ${label} · PASS`);
  }
  const text = await log.innerText();
  for (const siteId of [1, 2]) {
    const evidence = `[EVIDENCE] Site interface: openocd · PPU z2 · PPU ID z2-hil · SITE-0${siteId}`;
    expect(text.split(evidence).length - 1).toBe(1);
  }
  // The [RUN] line names the target once (the appended label), not twice.
  expect(text).not.toMatch(/· PPU z2 · Site \d+ · SAFE_OFF/);
  // The Log shows the newest line first: TERMINAL is written after every
  // Site's run lines, including a Site whose run was read by run_id.
  await expect(log).toContainText("[BAT] TERMINAL · SUCCESS");
  const ordered = await log.innerText();
  expect(ordered.indexOf("[BAT] TERMINAL")).toBeLessThan(ordered.indexOf("[RUN] PASS"));
  expect(ordered.indexOf("[BAT] TERMINAL")).toBeLessThan(ordered.indexOf("[SITE] PPU z2"));
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(2);
});


for (const count of [1, 2, 8]) {
  test(`${count} concurrent Sites display 16s Batch wall-clock and retain it after reload`, async ({ page }) => {
    const sites = Array.from({ length: count }, (_, i) => i + 1);
    const counters = await mockManager(page, {
      ppus: [{ ...Z2, enabledSites: sites }], concurrentLanes: true,
      batchTiming: { startedAt: "2026-11-16T12:00:00+00:00", finishedAt: "2026-11-16T12:00:16+00:00" },
    });
    const { start } = await prepare(page, [["z2", sites]]);
    await start.click();
    await finished(page);
    const time = page.locator('[data-kpi="batch-time"]');
    await expect(time).toContainText("00:00:16");
    await page.reload();
    await expect(time).toContainText("00:00:16");
    expect(counters.batches).toHaveLength(1);
    expect(counters.jobs).toHaveLength(count);
  });
}

test("running Manager Batch Time ticks without another submission and refresh resumes it", async ({ page }) => {
  const startedAt = new Date(Date.now() - 5000).toISOString();
  const counters = await mockManager(page, {
    script: () => ({ runningPolls: 1000 }),
    batchTiming: { startedAt, finishedAt: new Date().toISOString() },
  });
  const { start } = await prepare(page, [["z2", [2]]]);
  await start.click();
  const time = page.locator('[data-kpi="batch-time"]');
  await expect(time).not.toContainText("UNKNOWN");
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/RUNNING/);
  const before = await time.innerText();
  await expect.poll(() => time.innerText()).not.toBe(before);
  await page.reload();
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/RUNNING/);
  await expect(time).not.toContainText("UNKNOWN");
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(1);
});


test("a lost Start reconciled after completion retains terminal Batch Time on reload", async ({ page }) => {
  const counters = await mockManager(page, { batchLost: true });
  const { start } = await prepare(page, [["z2", [2]]]);
  await start.click();
  await expect(page.getByTestId("managed-readiness")).toContainText("START RECONCILIATION REQUIRED");
  await page.getByRole("button", { name: "RECONCILE MANAGER START" }).click();
  await finished(page);
  const time = page.locator('[data-kpi="batch-time"]');
  await expect(time).toContainText("00:00:16");
  await page.reload();
  await expect(time).toContainText("00:00:16");
  expect(counters.batches).toHaveLength(1);
  expect(counters.issued).toHaveLength(1);
  expect(counters.jobs).toHaveLength(1);
});

test("Manual Repeat: with two Sites waiting, START continues only the tile marked as replaced", async ({ page }) => {
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2] }] });
  const { job, start } = await prepare(page, [["z2", [1, 2]]]);
  await job.getByLabel("Repeat Count").fill("3");
  const continues: Array<Record<string, unknown>> = [];
  const waitingSites = new Set([1, 2]);
  let started: Record<string, unknown> = {};
  const unit = (siteId: number) => {
    const waiting = waitingSites.has(siteId);
    return {
      ppu_alias: "z2", site_id: siteId, status: waiting ? "AWAITING_CONTINUE" : "RUNNING",
      outcome: null, reason: null, failure_domain: null, attempts: [], progress: null,
      cycle: {
        planned: 3, index: 2, cycle_id: `${siteId}`.repeat(32), state: waiting ? "AWAITING_CONTINUE" : "ACTIVE",
        disposition: null, settled: 1, pass: 0, fail: 1, retry_attempts: 0, remaining: 2,
        continue_seq: 1, continued_seq: waiting ? 0 : 1, wait_reason: waiting ? "FAIL_REVIEW" : null,
        last: { cycle_index: 1, cycle_id: "a".repeat(32), outcome: "FAIL", reason: "JOB_NOT_SUCCESS",
          attempts: 1, receipt: null },
      },
    };
  };
  const view = () => ({
    schema: "plasma.manager.programming-batch.v2", batch_id: "9".repeat(32), start_id: started.start_id,
    targets: started.targets, icpn: started.icpn, operations: started.operations, source: "image",
    policy: { repeat: 3, replace_ic_before_next_cycle: true, retry_limit: 0, stop_policy: { kind: "never" } },
    state: "running", execution_status: "RUNNING", outcome: null, reason: null, failure_domain: null,
    stop_requested: false, units: [unit(1), unit(2)], attempts: [], current_run: null,
    counts: { pass: 0, fail: 0, blocked: 0, unknown: 0, sites: 2, attempts: 0 },
    cycles: { planned: 6, settled: 2, pass: 0, fail: 2, retry_attempts: 0, remaining: 4,
      awaiting_continue: waitingSites.size },
    auto_retry: "DISABLED", created_at: null, started_at: null, finished_at: null,
  });
  await page.route(/\/api\/manager\/programming\/batches$/, async route => {
    started = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, json: { ok: true, batch: view() } });
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}$/, async route => {
    await route.fulfill({ json: { ok: true, batch: view() } });
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}\/continue$/, async route => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    continues.push(body);
    waitingSites.delete(Number(body.site_id));
    await route.fulfill({ json: { ok: true, duplicate: false, batch: view() } });
  });
  await start.click();
  await expect(job.getByRole("button", { name: /MARK THE REPLACED SITE/ })).toBeDisabled();
  // Rounds are settled Cycles (FAIL included); PASS and FAIL stay separate.
  await expect(summary(page)).toContainText(/PROCESSED IC\s*2/);
  await page.getByLabel(/SITE-01 IC replaced$/).check();
  await job.getByRole("button", { name: /CONTINUE z2 SITE-01$/ }).click();
  await expect.poll(() => continues.length).toBe(1);
  expect(continues).toEqual([{ ppu_alias: "z2", site_id: 1, continue_seq: 1 }]);
  await expect(job.getByRole("button", { name: /MARK THE REPLACED SITE/ })).toBeDisabled();
  await page.waitForTimeout(1500);
  expect(continues).toHaveLength(1);
});

// ---------------------------------------------------------------------------
// Repeat evidence logging: Run Outcome, Cycle Outcome, Site Lane and Batch
// Outcome are separate lifecycles. A Cycle's PASS run while its Site Lane is
// still open (RUNNING / AWAITING_CONTINUE) is a normal intermediate state,
// never an Evidence ERROR; a Receipt that fails `runVerdict` still is.
// Scripted Manager views at the Browser boundary - host-only, not hardware.
// ---------------------------------------------------------------------------

type Tamper = "identity";
type ScriptedAttempt = { cycle: number; attempt: number; outcome: "PASS" | "FAIL" | "OUTCOME_UNKNOWN" | null;
  tamper?: Tamper; retry?: boolean };
type ScriptedLane = { siteId: number; attempts: ScriptedAttempt[]; outcome: string | null;
  cycle: { index: number; state: "ACTIVE" | "AWAITING_CONTINUE" | "ENDED"; settled: number; pass: number; fail: number;
    continueSeq: number; continuedSeq: number; waitReason: string | null } };

const IMAGE_SHA = sha("1");
const runIdOf = (siteId: number, a: ScriptedAttempt) => `${siteId}${a.cycle}${a.attempt}`.padStart(32, "0");
const jobIdOf = (siteId: number, a: ScriptedAttempt) => `job-s${siteId}-c${a.cycle}-a${a.attempt}`;
const bindingOf = (siteId: number) => sha(String(siteId + 2));

async function repeatManager(page: Page, options: { repeat?: number; replaceIc?: boolean; sites?: number[] } = {}) {
  const repeat = options.repeat ?? 10;
  const sites = options.sites ?? [1, 2];
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: sites }] });
  const batchId = "7".repeat(32);
  const lanes: ScriptedLane[] = sites.map(siteId => ({ siteId, attempts: [{ cycle: 1, attempt: 1, outcome: null }], outcome: null,
    cycle: { index: 1, state: "ACTIVE", settled: 0, pass: 0, fail: 0, continueSeq: 0, continuedSeq: 0, waitReason: null } }));
  const history: Array<Record<string, unknown>> = [];
  const continues: Array<Record<string, unknown>> = [];
  const runReads: string[] = [];
  let started: Record<string, unknown> = {};
  let outcome: string | null = null;

  const run = (lane: ScriptedLane, a: ScriptedAttempt) => {
    const operations = started.operations as string[];
    const binding = bindingOf(lane.siteId);
    return {
      schema: "plasma.manager.bundle-programming-run.v1", run_id: runIdOf(lane.siteId, a), ppu_alias: "z2", site_id: lane.siteId,
      state: a.outcome ? "finished" : "running", outcome: a.outcome,
      reason: a.outcome === "PASS" || a.outcome == null ? null : a.outcome === "FAIL" ? "JOB_NOT_SUCCESS" : "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT",
      created_at: "t", updated_at: "t", steps: [{ step: "PREFLIGHT", result: "PASS", at: "t" }], activation: {},
      job: { job_id: jobIdOf(lane.siteId, a), state: a.outcome ? "finished" : "running", stage: "programming",
        progress_percent: a.outcome ? 100 : 40, attempt: 1 },
      receipt: a.outcome !== "PASS" && a.outcome !== "FAIL" ? null : {
        schema: "plasma.manager.programming-receipt.v3", job_id: jobIdOf(lane.siteId, a), job_state: "success",
        operation: "programming", operations, observed_operations: operations, site_id: lane.siteId, target: "STM32F103C8T6",
        range: { address: 134217728, length: 4096 }, expected_image_sha256: IMAGE_SHA, expected_image_size: 4096,
        readback_sha256: IMAGE_SHA, bytes_verified: 4096,
        expected_resource_set_sha256: RESOURCE_SHA, observed_resource_set_sha256: RESOURCE_SHA,
        expected_job_binding_sha256: binding, observed_job_binding_sha256: binding,
        resource_reuse: true, safe_off: true, safe_off_state: "VERIFIED",
        flash_result: a.outcome, elapsed_ms: 7000,
      },
      job_submission_count: 1, auto_retry: "DISABLED", acknowledged: false,
    };
  };
  const attemptOf = (lane: ScriptedLane, a: ScriptedAttempt) => ({
    attempt: a.attempt, cycle_index: a.cycle,
    job_key: { batch_id: batchId, ppu_alias: "z2", site_id: a.tamper === "identity" ? 99 : lane.siteId, cycle: a.cycle, attempt: a.attempt },
    plan_id: `plan-${runIdOf(lane.siteId, a)}`, run_id: runIdOf(lane.siteId, a), job_id: jobIdOf(lane.siteId, a),
    job_binding_sha256: bindingOf(lane.siteId), state: a.outcome ? "finished" : "running", outcome: a.outcome,
    reason: a.outcome === "FAIL" ? "JOB_NOT_SUCCESS" : null, safe_off: a.outcome === "OUTCOME_UNKNOWN" ? null : a.outcome ? true : null,
    safe_off_state: a.outcome && a.outcome !== "OUTCOME_UNKNOWN" ? "VERIFIED" : null,
    retry: a.retry ? { eligible: true, reason: "DEFINITE_FAIL_SAFE_OFF_VERIFIED", decision: "RETRY" } : null,
  });
  const view = () => {
    const units = lanes.map(lane => {
      const current = lane.attempts.filter(a => a.cycle === lane.cycle.index || lane.cycle.state !== "ACTIVE");
      return {
        ppu_alias: "z2", site_id: lane.siteId, status: lane.outcome ? "COMPLETED" : lane.cycle.state === "AWAITING_CONTINUE" ? "AWAITING_CONTINUE" : "RUNNING",
        outcome: lane.outcome, reason: lane.outcome && lane.outcome !== "PASS" ? "JOB_NOT_SUCCESS" : null, failure_domain: null,
        attempts: current.slice(current.findIndex(a => a.cycle === current[current.length - 1].cycle)).map(a => attemptOf(lane, a)),
        progress: null,
        cycle: { planned: repeat, index: lane.cycle.index, cycle_id: `${lane.siteId}${lane.cycle.index}`.padStart(32, "0"),
          state: lane.cycle.state, disposition: lane.outcome, settled: lane.cycle.settled, pass: lane.cycle.pass, fail: lane.cycle.fail,
          retry_attempts: lane.attempts.filter(a => a.attempt > 1).length, attempts: lane.attempts.length,
          remaining: repeat - lane.cycle.settled, continue_seq: lane.cycle.continueSeq, continued_seq: lane.cycle.continuedSeq,
          wait_reason: lane.cycle.waitReason, last: null },
      };
    });
    const first = lanes[0];
    const settled = lanes.reduce((total, lane) => total + lane.cycle.settled, 0);
    return {
      schema: "plasma.manager.programming-batch.v2", batch_id: batchId, start_id: started.start_id,
      targets: started.targets, icpn: started.icpn, operations: started.operations, source: "image",
      policy: { repeat, replace_ic_before_next_cycle: options.replaceIc ?? true, retry_limit: 3, stop_policy: { kind: "never" } },
      state: outcome ? "finished" : "running", execution_status: outcome ? "COMPLETED" : "RUNNING", outcome, reason: null,
      failure_domain: null, stop_requested: false, units, attempts: units.flatMap(unit => unit.attempts),
      current_run: run(first, first.attempts[first.attempts.length - 1]),
      counts: { pass: lanes.filter(lane => lane.outcome === "PASS").length, fail: lanes.filter(lane => lane.outcome === "FAIL").length,
        blocked: 0, unknown: 0, sites: lanes.length, attempts: lanes.reduce((total, lane) => total + lane.attempts.length, 0) },
      cycles: { planned: repeat * lanes.length, settled, pass: lanes.reduce((t, l) => t + l.cycle.pass, 0),
        fail: lanes.reduce((t, l) => t + l.cycle.fail, 0), retry_attempts: 0, remaining: repeat * lanes.length - settled,
        attempts: lanes.reduce((total, lane) => total + lane.attempts.length, 0),
        awaiting_continue: lanes.filter(lane => lane.cycle.state === "AWAITING_CONTINUE").length },
      auto_retry: "DISABLED", created_at: null, started_at: "2026-11-23T00:00:00+00:00", finished_at: outcome ? "2026-11-23T00:01:00+00:00" : null,
    };
  };
  await page.route(/\/api\/manager\/programming\/batches$/, async route => {
    started = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, json: { ok: true, batch: view() } });
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}$/, route => route.fulfill({ json: { ok: true, batch: view() } }));
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}\/continue$/, async route => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    continues.push(body);
    await route.fulfill({ json: { ok: true, duplicate: false, batch: view() } });
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}\/cycles\?/, async route => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset"));
    const records = history.slice(offset);
    await route.fulfill({ json: { ok: true, batch_id: batchId, total: history.length, offset, next_offset: offset + records.length, records } });
  });
  // A Site's run read by run_id: only runs the scripted lanes hold.
  await page.route(/\/bootstrap\/programming\/runs\/[0-9a-f]{32}$/, async route => {
    const runId = new URL(route.request().url()).pathname.split("/").pop()!;
    runReads.push(runId);
    for (const lane of lanes) {
      const found = lane.attempts.find(a => runIdOf(lane.siteId, a) === runId);
      if (found) return route.fulfill({ json: { ok: true, run: run(lane, found) } });
    }
    await route.fulfill({ status: 404, json: { ok: false, error: { code: "programming_run_not_found", message: "no such run" } } });
  });

  const lane = (siteId: number) => lanes.find(item => item.siteId === siteId)!;
  /** The Manager settles a Cycle of one Site and appends its History record. */
  const settle = (siteId: number, next: "AWAITING_CONTINUE" | "ACTIVE" | "ENDED") => {
    const item = lane(siteId);
    const cycleAttempts = item.attempts.filter(a => a.cycle === item.cycle.index);
    const last = cycleAttempts[cycleAttempts.length - 1];
    const passed = last.outcome === "PASS";
    item.cycle.settled += 1;
    if (passed) item.cycle.pass += 1; else item.cycle.fail += 1;
    history.push({ seq: history.length, type: "cycle", batch_id: batchId, ppu_alias: "z2", site_id: siteId,
      cycle_index: item.cycle.index, outcome: last.outcome, reason: passed ? null : "JOB_NOT_SUCCESS",
      attempts: cycleAttempts.map(a => ({ ...attemptOf(item, a) })),
      receipt: { run_id: runIdOf(siteId, last), job_id: jobIdOf(siteId, last), job_state: "success", safe_off: true,
        safe_off_state: "VERIFIED", job_binding_confirmed: true, readback_sha256: IMAGE_SHA, job_binding_sha256: bindingOf(siteId) } });
    if (next === "AWAITING_CONTINUE") {
      item.cycle.state = "AWAITING_CONTINUE";
      item.cycle.continueSeq += 1;
      item.cycle.waitReason = passed ? "REPLACE_IC" : "FAIL_REVIEW";
    } else if (next === "ACTIVE") {
      item.cycle.index += 1;
      item.attempts.push({ cycle: item.cycle.index, attempt: 1, outcome: null });
    } else {
      item.cycle.state = "ENDED";
      item.outcome = passed ? "PASS" : "FAIL";
    }
  };
  /** Operator Continue reached the Manager: the next Cycle starts on that Site only. */
  const resume = (siteId: number) => {
    const item = lane(siteId);
    history.push({ seq: history.length, type: "continue", batch_id: batchId, ppu_alias: "z2", site_id: siteId,
      continue_seq: item.cycle.continueSeq, after_cycle_index: item.cycle.index, wait_reason: item.cycle.waitReason });
    item.cycle.continuedSeq = item.cycle.continueSeq;
    item.cycle.state = "ACTIVE";
    item.cycle.waitReason = null;
    item.cycle.index += 1;
    item.attempts.push({ cycle: item.cycle.index, attempt: 1, outcome: null });
  };
  const finishAttempt = (siteId: number, result: "PASS" | "FAIL" | "OUTCOME_UNKNOWN", tamper?: Tamper) => {
    const item = lane(siteId);
    Object.assign(item.attempts[item.attempts.length - 1], { outcome: result, tamper });
  };
  const retry = (siteId: number) => {
    const item = lane(siteId);
    const last = item.attempts[item.attempts.length - 1];
    last.retry = true;
    item.attempts.push({ cycle: last.cycle, attempt: last.attempt + 1, outcome: null });
  };
  return { lane, settle, resume, finishAttempt, retry, continues, runReads,
    end: (value: string) => { outcome = value; } };
}

async function startRepeat(page: Page, repeat = "10", replaceIc = true) {
  const { job, start } = await prepare(page, [["z2", [1, 2]]]);
  await job.getByLabel("Repeat Count").fill(repeat);
  await job.getByLabel("Site Retry Limit").fill("3");
  if (!replaceIc) await job.getByLabel("Replace IC before next Cycle").uncheck();
  await start.click();
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/RUNNING|WAITING/);
  return job;
}

const logLines = async (page: Page, pattern: RegExp) =>
  (await factoryLog(page).locator("span").allInnerTexts()).filter(line => pattern.test(line));
const errorLines = (page: Page) => factoryLog(page).locator('span[data-level="error"]').allInnerTexts();
/** Let the 250 ms poll run several times over an unchanged Manager view. */
const settlePolls = (page: Page) => page.waitForTimeout(1500);

test("Repeat 10: Cycle 1 PASS while each Site Lane is open is not an Evidence ERROR; each wait is logged once", async ({ page }) => {
  const manager = await repeatManager(page);
  await startRepeat(page);
  manager.finishAttempt(1, "PASS");
  manager.finishAttempt(2, "PASS");
  // Site 1: Cycle 1 settled, its Lane still RUNNING (before the wait); Site 2: waiting for a replaced IC.
  manager.settle(2, "AWAITING_CONTINUE");
  await expect(factoryLog(page)).toContainText(/\[CYCLE 1\/10\] PPU z2 .* SITE-02 · PASS/);
  await expect(factoryLog(page)).toContainText(/\[SITE\] PPU z2 .* SITE-02 · Cycle 1\/10 · PASS 1 .* REPLACE IC · press Start/);
  manager.settle(1, "AWAITING_CONTINUE");
  await expect(factoryLog(page)).toContainText(/\[CYCLE 1\/10\] PPU z2 .* SITE-01 · PASS/);
  await expect(factoryLog(page)).toContainText(/SITE-01 · Cycle 1\/10 .* REPLACE IC · press Start/);
  await settlePolls(page);
  await expect(factoryLog(page)).not.toContainText("PASS REJECTED");
  await expect(factoryLog(page)).not.toContainText(/\[SITE\] .* · RUNNING/);
  expect(await errorLines(page)).toEqual([]);
  // Same polling events never repeat a line.
  expect(await logLines(page, /\[CYCLE 1\/10\]/)).toHaveLength(2);
  expect(await logLines(page, /REPLACE IC · press Start/)).toHaveLength(2);
  // Each Site is continued on its own; the other keeps waiting.
  await page.getByLabel(/SITE-02 IC replaced$/).check();
  await page.getByRole("button", { name: /CONTINUE z2 SITE-02$/ }).click();
  await expect.poll(() => manager.continues.length).toBe(1);
  expect(manager.continues[0]).toMatchObject({ ppu_alias: "z2", site_id: 2, continue_seq: 1 });
  manager.resume(2);
  manager.finishAttempt(2, "PASS");
  manager.settle(2, "AWAITING_CONTINUE");
  await expect(factoryLog(page)).toContainText(/\[CYCLE 2\/10\] PPU z2 .* SITE-02 · PASS/);
  await expect(factoryLog(page)).toContainText(/\[CONTINUE\] PPU z2 .* SITE-02 · after Cycle 1 · REPLACE_IC/);
  expect(await logLines(page, /SITE-01 · Cycle .* REPLACE IC · press Start/)).toHaveLength(1);
  expect(await logLines(page, /SITE-02 · Cycle 2\/10 .* REPLACE IC · press Start/)).toHaveLength(1);
  expect(manager.continues).toHaveLength(1);
  // A reload rebuilds the Log from the Manager: still no Evidence ERROR, no duplicates.
  await page.reload();
  await expect(factoryLog(page)).toContainText(/\[CYCLE 2\/10\] PPU z2 .* SITE-02 · PASS/);
  await settlePolls(page);
  expect(await errorLines(page)).toEqual([]);
  expect(await logLines(page, /\[CYCLE 1\/10\]/)).toHaveLength(2);
  expect(await logLines(page, /\[CYCLE 2\/10\]/)).toHaveLength(1);
});

test("Repeat same-IC Debug: PASS Cycles continue without a Continue; each Cycle's run is judged by run_id", async ({ page }) => {
  const manager = await repeatManager(page, { repeat: 3, replaceIc: false });
  await startRepeat(page, "3", false);
  manager.finishAttempt(1, "PASS");
  manager.settle(1, "ACTIVE");
  manager.finishAttempt(2, "PASS");
  manager.settle(2, "ACTIVE");
  await expect(factoryLog(page)).toContainText(/\[CYCLE 1\/3\] PPU z2 .* SITE-02 · PASS/);
  // Cycle 2 restarts at attempt 1: its run is a different record, judged on its own.
  manager.finishAttempt(2, "PASS");
  await settlePolls(page);
  expect(manager.continues).toEqual([]);
  expect(await logLines(page, /PASS REJECTED/)).toHaveLength(0);
  expect((await errorLines(page)).filter(line => line.includes("SITE-01"))).toEqual([]);
  await expect(factoryLog(page)).not.toContainText("press Start");
});

test("Repeat with Retry: a FAIL attempt then a legal Retry PASS keeps both in the Log", async ({ page }) => {
  const manager = await repeatManager(page);
  await startRepeat(page);
  manager.finishAttempt(1, "FAIL");
  await expect(factoryLog(page)).toContainText(/\[RUN\] FAIL · JOB_NOT_SUCCESS .* SITE-01/);
  manager.retry(1);
  manager.finishAttempt(1, "PASS");
  manager.settle(1, "AWAITING_CONTINUE");
  await expect(factoryLog(page)).toContainText(/\[CYCLE 1\/10\] PPU z2 .* SITE-01 · PASS .* attempts 2/);
  await expect(factoryLog(page)).toContainText(/\[ATTEMPT 1\] Cycle 1\/10 PPU z2 .* SITE-01 · FAIL .* RETRY/);
  await expect(factoryLog(page)).toContainText(/\[ATTEMPT 2\] Cycle 1\/10 PPU z2 .* SITE-01 · PASS/);
  await settlePolls(page);
  await expect(factoryLog(page)).not.toContainText("PASS REJECTED");
  expect(await logLines(page, /\[RUN\] FAIL · JOB_NOT_SUCCESS/)).toHaveLength(1);
});

// U9: the Manager judges the receipt; the Browser only refuses a record that
// names another Site (ATTEMPT_IDENTITY_MISMATCH).
for (const [tamper, reason] of [
  ["identity", "ATTEMPT_IDENTITY_MISMATCH"],
] as const) {
  test(`Repeat: an open Site Lane still rejects a Manager PASS with ${reason}, only on that Site`, async ({ page }) => {
    const manager = await repeatManager(page);
    await startRepeat(page);
    manager.finishAttempt(1, "PASS");
    // Site 2 is NOT the Batch's current_run: its run is read by run_id.
    manager.finishAttempt(2, "PASS", tamper);
    await expect(factoryLog(page)).toContainText(new RegExp(`MANAGER RUN PASS REJECTED · ${reason} · PPU z2 .* SITE-02`));
    await settlePolls(page);
    expect(await logLines(page, /PASS REJECTED/)).toHaveLength(1);
    expect((await errorLines(page)).filter(line => line.includes("SITE-01"))).toEqual([]);
  });
}

test("Repeat: OUTCOME_UNKNOWN on an open Lane is reported, never PASS, and nothing is resubmitted", async ({ page }) => {
  const manager = await repeatManager(page);
  await startRepeat(page);
  manager.finishAttempt(2, "OUTCOME_UNKNOWN");
  await expect(factoryLog(page)).toContainText(/\[RUN\] OUTCOME UNKNOWN .* SITE-02/);
  await settlePolls(page);
  expect(await logLines(page, /SITE-02 · PASS|\[CYCLE 1\/10\] .* SITE-02/)).toEqual([]);
  expect(await logLines(page, /\[RUN\] OUTCOME UNKNOWN/)).toHaveLength(1);
  expect(manager.continues).toEqual([]);
});

test("Repeat ends: the final Site and Batch outcomes are logged once", async ({ page }) => {
  const manager = await repeatManager(page, { repeat: 2, replaceIc: false });
  await startRepeat(page, "2", false);
  for (const siteId of [1, 2]) {
    manager.finishAttempt(siteId, "PASS");
    manager.settle(siteId, "ACTIVE");
    manager.finishAttempt(siteId, "PASS");
    manager.settle(siteId, "ENDED");
  }
  manager.end("PASS");
  await finished(page);
  await expect(factoryLog(page)).toContainText(/\[BAT\] TERMINAL · SUCCESS/);
  expect(await logLines(page, /\[SITE\] PPU z2 .* · PASS · Run/)).toHaveLength(2);
  expect(await logLines(page, /\[CYCLE [12]\/2\]/)).toHaveLength(4);
  expect(await errorLines(page)).toEqual([]);
});
