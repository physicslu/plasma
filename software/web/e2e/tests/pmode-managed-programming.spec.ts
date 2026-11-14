import { expect, test, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, Z2, legacyRequests, mockManager, type Counters, type MockPpu, type RunScript,
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
  await expect(job.getByLabel("Repeat Count")).toBeDisabled();
  await expect(job.getByLabel("Repeat Count")).toHaveValue("1");
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
  await expect(page.getByText("Resource Set mismatch")).toBeVisible();
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
  expect(counters.starts.length).toBeGreaterThanOrEqual(1);
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
