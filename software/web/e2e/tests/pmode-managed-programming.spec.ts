import { expect, test, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, Z2, legacyRequests, mockManager, route, type Counters, type MockPpu, type RunScript,
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
const receipt = (page: Page, alias: string, siteId: number) => page.locator(`[data-receipt-site="${alias}:${siteId}"]`);
const writes = (counters: Counters) => counters.mutations.filter(entry => !entry.endsWith("/api/manager/ppu"));

async function finished(page: Page) {
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/SUCCESS|PARTIAL|ERROR|CANCELLED/, { timeout: 30_000 });
}

test("registered PPUs are discovered from the Manager; ONLINE no longer means Programming unavailable", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2, { alias: "spare", ppuId: "spare-01", lifecycle: "pending" }] });
  await openFactory(page);
  await expect(page.getByLabel("Factory communication health")).toContainText("Gateway ONLINE");
  await expect(page.getByLabel("Factory communication health")).not.toContainText("PROGRAMMING UNAVAILABLE");
  const tree = page.locator(".productionTreePpu");
  await expect(tree).toHaveCount(2); // the pending Registry entry is a Registration concern
  await expect(tree.nth(0)).toContainText("z2 · PPU ID z2-hil");
  await expect(tree.nth(1)).toContainText("line2 · PPU ID line2-01");
  expect(legacyRequests(counters)).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("ONLINE and Programming capability are separate: a Site without a Route blocks Start with the exact Site", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2] }] });
  const { start } = await prepare(page, [["z2", [1, 2]]]);
  await expect(page.getByLabel("Factory communication health")).toContainText("Gateway ONLINE");
  const readiness = page.getByTestId("managed-readiness");
  await expect(readiness).toContainText("PROGRAMMING UNAVAILABLE");
  await expect(readiness).toContainText("PPU z2 Site 1");
  await expect(readiness).toContainText("No Programming Route declares STM32F103C8T6 on Site 1");
  await expect(start).toBeDisabled();
  // site_count = 8 never makes eight Sites programmable.
  expect(writes(counters)).toEqual([]);
});

test("multi-PPU production: one Manager run per PPU/Site with isolated Job, Resource and Binding identities", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await expect(start).toBeEnabled();
  await start.dblclick(); // a double click still starts one batch
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/SUCCESS/);
  expect(counters.plans.map(item => [item.alias, item.body.site_id])).toEqual([["z2", 2], ["line2", 2]]);
  expect(counters.starts.map(item => item.alias)).toEqual(["z2", "line2"]);
  // Each start consumes its own plan on its own PPU.
  expect(new Set(counters.starts.map(item => item.body.plan_id)).size).toBe(2);
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(summary(page)).toContainText("100.0%");
  await receipt(page, "z2", 2).locator("summary").click();
  await receipt(page, "line2", 2).locator("summary").click();
  await expect(receipt(page, "z2", 2).getByTestId("receipt-job")).toHaveText(/^job-z2-site2-/);
  await expect(receipt(page, "line2", 2).getByTestId("receipt-job")).toHaveText(/^job-line2-site2-/);
  await expect(receipt(page, "z2", 2).getByTestId("receipt-binding-sha")).toHaveText(/^z2-site2-plan1/);
  await expect(receipt(page, "line2", 2).getByTestId("receipt-binding-sha")).toHaveText(/^line2-site2-plan2/);
  await expect(receipt(page, "z2", 2).getByTestId("run-policy")).toContainText("PPU z2 · Site 2 · attempts 1 · auto retry DISABLED");
  await expect(receipt(page, "line2", 2).getByTestId("receipt-safe-off")).toHaveText("VERIFIED");
  expect(legacyRequests(counters)).toEqual([]);
});

test("multi-Site PASS / FAIL / Yield: a failed Site is counted once and never retried", async ({ page }) => {
  const script = (_alias: string, siteId: number): RunScript =>
    siteId === 1 ? {} : { outcome: "FAIL", reason: "READBACK_SHA256_MISMATCH" };
  const counters = await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2] }], routes: [route([1, 2])], script });
  const { start } = await prepare(page, [["z2", [1, 2]]]);
  await start.click();
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/PARTIAL/);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "faulted");
  await expect(summary(page)).toContainText("50.0%");
  await expect(receipt(page, "z2", 2)).toContainText("READBACK_SHA256_MISMATCH");
  await page.waitForTimeout(1500);
  expect(counters.plans).toHaveLength(2);
  expect(counters.starts).toHaveLength(2);
  // Per-Site plans: a Binding is never shared between Sites.
  expect(counters.plans.map(item => item.body.site_id)).toEqual([1, 2]);
});

test("OUTCOME_UNKNOWN latches only its own PPU: no resubmission, later Sites of that PPU never start", async ({ page }) => {
  const script = (alias: string, siteId: number): RunScript => alias === "z2" && siteId === 1
    ? { outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT" } : {};
  const counters = await mockManager(page, {
    ppus: [{ ...Z2, enabledSites: [1, 2] }, LINE2], routes: [route([1, 2])], script });
  const { start } = await prepare(page, [["z2", [1, 2]], ["line2", [2]]]);
  await start.click();
  await finished(page);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "error");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "stopped");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(receipt(page, "z2", 1)).toContainText("nothing was resubmitted");
  await expect(receipt(page, "z2", 2)).toContainText("unresolved OUTCOME UNKNOWN");
  await page.waitForTimeout(1500);
  expect(counters.starts.map(item => [item.alias])).toEqual([["z2"], ["line2"]]);
  expect(counters.plans.map(item => [item.alias, item.body.site_id])).toEqual([["z2", 1], ["line2", 2]]);
  // An unknown outcome is not a FAIL and not a PASS in the Yield.
  await expect(summary(page)).toContainText("100.0%");
});

test("an Offline PPU blocks Start with the exact reason and no write", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, { ...LINE2, transport: "unreachable" }] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  const readiness = page.getByTestId("managed-readiness");
  await expect(readiness).toContainText("PPU OFFLINE");
  await expect(readiness).toContainText("PPU line2");
  await expect(start).toBeDisabled();
  expect(writes(counters)).toEqual([]);
});

test("partial batch: a PPU in Recovery is blocked before any Job while the healthy PPU completes", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, { ...LINE2, deploymentState: "recovery_required" }] });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await start.click();
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/PARTIAL/);
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "error");
  await expect(receipt(page, "line2", 2)).toContainText("BLOCKED before any Job");
  await expect(receipt(page, "line2", 2)).toContainText("RECOVERY REQUIRED");
  expect(counters.plans.map(item => item.alias)).toEqual(["z2"]);
  expect(counters.starts.map(item => item.alias)).toEqual(["z2"]);
  expect(counters.requests.filter(entry => /enrollment|recovery/.test(entry))).toEqual([]);
});

test("Stop Policy only prevents further starts: no retry and no duplicate programming", async ({ page }) => {
  const counters = await mockManager(page, {
    ppus: [{ ...Z2, enabledSites: [1, 2] }, LINE2], routes: [route([1, 2])],
    script: () => ({ outcome: "FAIL", reason: "FLASH_CYCLE_NOT_PASS" }) });
  const { job, start } = await prepare(page, [["z2", [1, 2]], ["line2", [2]]]);
  await job.getByLabel("Stop Policy").selectOption("1");
  await start.click();
  await finished(page);
  await expect(site(page, "z2", 1)).toHaveAttribute("data-site-state", "faulted");
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "stopped");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "stopped");
  await expect(receipt(page, "line2", 2)).toContainText("Stop Policy reached 1 failed Site(s)");
  await page.waitForTimeout(1500);
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
});

test("ABORT stops queuing; the submitted run is observed to its end and nothing is cancelled or resent", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2], script: () => ({ runningPolls: 3 }) });
  const { job, start } = await prepare(page, [["z2", [2]], ["line2", [2]]]);
  await start.click();
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "running");
  await job.getByRole("button", { name: /ABORT/ }).click();
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/CANCELLED/);
  await expect(site(page, "z2", 2)).toHaveAttribute("data-site-state", "success");
  await expect(site(page, "line2", 2)).toHaveAttribute("data-site-state", "cancelled");
  expect(counters.starts.map(item => item.alias)).toEqual(["z2"]);
  expect(counters.mutations.filter(entry => /cancel|abort/.test(entry))).toEqual([]);
});

test("Image is the default Source; switching to Bundle clears the file and issues no request", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2] });
  const { job, start } = await prepare(page, [["z2", [2]]]);
  await expect(job.getByRole("radio", { name: "Image", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(start).toBeEnabled();
  await expect(job.getByLabel("Site Retry Limit")).toBeDisabled();
  await expect(job.getByLabel("Site Retry Limit")).toHaveValue("0");
  await expect(job.getByLabel("Repeat Count")).toBeDisabled();
  const operations = job.locator("[data-programming-job-operation]");
  await expect(operations).toHaveCount(1);
  await expect(operations).toHaveAttribute("data-programming-job-operation", "flash_cycle");
  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await expect(job.locator("[data-image-source]")).toHaveAttribute("data-image-source", "none");
  await expect(page.getByTestId("managed-readiness")).toContainText("BUNDLE REQUIRED");
  await expect(start).toBeDisabled();
  expect(writes(counters)).toEqual([]);
});

test("Bundle source production: every Site plan carries the user's Bundle bytes unchanged", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2], script: alias => ({ activationRequired: alias === "line2" }) });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]], "bundle");
  await start.click();
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/SUCCESS/);
  for (const planned of counters.plans) {
    expect(Buffer.from(String(planned.body.bundle_base64), "base64").equals(BUNDLE)).toBe(true);
    expect(planned.body).not.toHaveProperty("image_base64");
  }
  // Resource Reuse on one PPU and Admission on the other are independent decisions.
  await receipt(page, "z2", 2).locator("summary").click();
  await receipt(page, "line2", 2).locator("summary").click();
  await expect(receipt(page, "z2", 2).getByTestId("receipt-resource")).toHaveText("Reused");
  await expect(receipt(page, "line2", 2).getByTestId("receipt-resource")).toHaveText("Activated");
});

test("an incompatible Bundle fails closed on every Site without a single Job", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, LINE2], script: () => ({
    planError: { code: "bundle_resource_not_qualified", message: "BUNDLE_RESOURCE_NOT_ROUTE" } }) });
  const { start } = await prepare(page, [["z2", [2]], ["line2", [2]]], "bundle");
  await start.click();
  await finished(page);
  await expect(page.getByRole("status", { name: "BATCH STATUS" })).toHaveText(/ERROR/);
  await expect(receipt(page, "z2", 2)).toContainText("bundle_resource_not_qualified");
  await expect(receipt(page, "line2", 2)).toContainText("BLOCKED before any Job");
  expect(counters.starts).toHaveLength(0);
});
