import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import {
  batchRuns,
  engineeringLog,
  engineeringSiteRow,
  harnessPpuState,
  imagePattern,
  managed,
  observeManagedTraffic,
  openEngineering,
  selectEngineeringIc,
  setEngineeringOperations,
  setEngineeringSites,
  setHarnessPpu,
  settledManagerBatch,
  type Operation,
} from "./mock-cd-managed-helpers";

// U10 Managed Lifecycle on the real Mock CD stack:
// Console → BFF → Manager ProgrammingBatchCoordinator → real PPU Bootstrap /
// Reservation / Job Binding → Mock PPU Runtime. No Plasma API is replaced.

const imageAssetBytes = imagePattern(256, 17, 3);
const imageFile = (name: string, buffer: Buffer = imageAssetBytes) =>
  ({ name, mimeType: "application/octet-stream", buffer });

test("Control Station root and retired /ppu route never expose the legacy Site Matrix", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByText("選擇產品模式", { exact: true })).toBeVisible();
  await expect(page.getByText("SITE MATRIX", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PPU CONTROL", { exact: true })).toHaveCount(0);

  await page.goto("/ppu");
  await expect(page).toHaveURL(/\/engineering$/);
  await expect(page.getByRole("button", { name: /^(Programming|燒錄)$/ }).first()).toBeVisible();
  await expect(page.getByText("SITE MATRIX", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PPU CONTROL", { exact: true })).toHaveCount(0);
});

test("Manager-managed PPU goes offline and recovers without reviving direct PPU Console ownership", async ({ page, request }) => {
  const alias = managed.ppuB;
  const traffic = observeManagedTraffic(page);
  const workspace = await openEngineering(page, alias);
  // The managed Console owns no Gateway URL: the PPU is a Manager Registry entry.
  await expect(page.getByLabel("Engineering Gateway URL")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Connect", exact: true })).toHaveCount(0);
  const foot = workspace.getByLabel("Selected Engineering PPU");
  await expect(foot).toContainText(`Manager Alias: ${alias}`);
  await expect(foot).toContainText("PPU ONLINE", { timeout: 30_000 });

  const job = await selectEngineeringIc(page);
  await setEngineeringSites(workspace, [1], managed.ppuBSites);
  await setEngineeringOperations(job, ["erase"]);
  const start = job.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(start).toBeEnabled();

  try {
    await setHarnessPpu(request, alias, "offline");
    // The Manager Fleet observes the unreachable PPU; the Console fails closed.
    await expect(foot).toContainText("PPU OFFLINE", { timeout: 45_000 });
    await expect(workspace.getByTestId("managed-readiness")).toContainText("PPU OFFLINE");
    await expect(start).toBeDisabled();
    // The Manager Registry itself stays reachable; only the PPU is offline.
    await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE");
  } finally {
    await setHarnessPpu(request, alias, "online");
  }

  await expect(foot).toContainText("PPU ONLINE", { timeout: 45_000 });
  expect((await harnessPpuState(request))[alias]?.state).toBe("online");
  await expect(start).toBeEnabled({ timeout: 30_000 });
  // Recovery alone never submits anything.
  expect(traffic.batches).toEqual([]);
  expect(traffic.legacy).toEqual([]);
});

test("EMode owns real per-Site E/P/V/R and Read download through the Manager Managed Lifecycle", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  // No Save File Picker: the verified Read is offered as a Browser download.
  await page.addInitScript(() => { (window as unknown as Record<string, unknown>).showSaveFilePicker = undefined; });
  const workspace = await openEngineering(page, managed.ppuA);
  const job = await selectEngineeringIc(page);
  const siteId = managed.ppuASites;
  await setEngineeringSites(workspace, [siteId], managed.ppuASites);
  await job.getByLabel("Engineering Programming Image file").setInputFiles(imageFile("engineering-managed-runtime.bin"));
  const start = job.getByRole("button", { name: /START PROGRAMMING/ });
  const row = engineeringSiteRow(workspace, siteId);
  const log = engineeringLog(workspace);

  // Erase-only and Read Batches carry no Image, so they never activate a
  // Resource Set (ADMISSION_RESOURCE_ACTIVATION_REQUIRES_IMAGE on a PPU with
  // no Active Set). Program first so this test does not depend on spec order;
  // then each of E / P / V runs as its own Batch on the Site.
  const perSiteOperations: Operation[] = ["program", "erase", "program", "verify"];
  for (const [index, operation] of perSiteOperations.entries()) {
    await test.step(`${managed.ppuA}/SITE-${siteId}: ${operation} (#${index + 1})`, async () => {
      const before = traffic.batches.length;
      await setEngineeringOperations(job, [operation]);
      await expect(start).toBeEnabled();
      await start.click();
      await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(before + 1);
      const sent = traffic.batches[before];
      expect(sent.body.targets).toEqual([{ ppu_alias: managed.ppuA, site_ids: [siteId] }]);
      expect(sent.body.operations).toEqual([operation]);
      await expect.poll(() => sent.batchId, { timeout: 15_000 }).toMatch(/^[0-9a-f]{32}$/);
      const batch = await settledManagerBatch(request, sent.batchId!);
      expect(batch.outcome).toBe("PASS");
      expect(batch.operations).toEqual([operation]);
      const runs = await batchRuns(request, batch);
      expect(runs).toHaveLength(1);
      expect(runs[0].run.outcome).toBe("PASS");
      expect(runs[0].run.site_id).toBe(siteId);
      expect(runs[0].run.receipt?.operations).toEqual([operation]);
      expect(runs[0].run.receipt?.observed_operations).toEqual([operation]);
      await expect(row.locator(".engineeringResult")).toHaveText("PASS", { timeout: 30_000 });
      await expect(log).toContainText(`[RESULT] PASS · Batch ${sent.batchId}`, { timeout: 30_000 });
    });
  }

  await test.step(`${managed.ppuA}/SITE-${siteId}: read`, async () => {
    const before = traffic.batches.length;
    const readButton = workspace.getByRole("button", { name: `Read SITE ${siteId} Flash` });
    await expect(readButton).toBeEnabled();
    await readButton.click();
    await expect(workspace.getByRole("status", { name: `SITE ${siteId} Read status` })).toHaveText("PASS", { timeout: 60_000 });
    await expect.poll(() => traffic.batches.length).toBe(before + 1);
    const sent = traffic.batches[before];
    // Read is address / length over the Route's whole Flash: its own one-Site Batch.
    expect(sent.body).toMatchObject({
      icpn: managed.icpn,
      targets: [{ ppu_alias: managed.ppuA, site_ids: [siteId] }],
      operation: "read",
      address: managed.flashBase,
      length: managed.flashSize,
    });
    expect(sent.body).not.toHaveProperty("operations");
    const batch = await settledManagerBatch(request, sent.batchId!);
    expect(batch.outcome).toBe("PASS");
    const [{ run }] = await batchRuns(request, batch);
    const output = run.receipt?.read_output;
    expect(output?.bytes).toBe(managed.flashSize);
    expect(output?.filename).toBeTruthy();

    const save = workspace.getByRole("link", { name: `Save SITE ${siteId} Read binary` });
    await expect(save).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
    // The file name is the Manager's Read output naming, not a Console invention.
    expect(download.suggestedFilename()).toBe(output!.filename);
    const path = await download.path();
    if (!path) throw new Error("Managed Mock PPU Read did not produce a local file");
    const bytes = await readFile(path);
    expect(bytes.length).toBe(managed.flashSize);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(output!.sha256);
    // Erase → Program → Verify left the Image at Flash Base and the rest erased.
    expect(bytes.subarray(0, imageAssetBytes.length).equals(imageAssetBytes)).toBe(true);
    expect(bytes.subarray(imageAssetBytes.length).every(value => value === 0xff)).toBe(true);
  });
  expect(traffic.legacy).toEqual([]);
});

test("EMode Manager Batch carries a non-contiguous Site subset × selected operations", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  const workspace = await openEngineering(page, managed.ppuA);
  const job = await selectEngineeringIc(page);
  const selectedSites = [1, 3, managed.ppuASites];
  const operations: Operation[] = ["erase", "program"];
  await setEngineeringSites(workspace, selectedSites, managed.ppuASites);
  await setEngineeringOperations(job, operations);
  // Read is a Site-row action, never a Programming Job operation.
  await expect(job.locator('[data-programming-job-operation="read"]')).toHaveCount(0);
  await job.getByLabel("Engineering Programming Image file").setInputFiles(imageFile("engineering-batch-runtime.bin"));

  const start = job.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(start).toBeEnabled();
  await start.click();
  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(1);

  const sent = traffic.batches[0];
  expect(sent.body.targets).toEqual([{ ppu_alias: managed.ppuA, site_ids: selectedSites }]);
  expect(sent.body.operations).toEqual(operations);
  await expect.poll(() => sent.batchId, { timeout: 15_000 }).toMatch(/^[0-9a-f]{32}$/);

  const batch = await settledManagerBatch(request, sent.batchId!);
  expect(batch.outcome).toBe("PASS");
  expect(batch.units.map(unit => [unit.ppu_alias, unit.site_id])).toEqual(
    selectedSites.map(siteId => [managed.ppuA, siteId]));
  const runs = await batchRuns(request, batch);
  expect(runs.map(item => item.run.site_id).sort((a, b) => a - b)).toEqual(selectedSites);
  for (const { run } of runs) {
    expect(run.outcome).toBe("PASS");
    expect(run.receipt?.operations).toEqual(operations);
    expect(run.receipt?.observed_operations).toEqual(operations);
  }

  const log = engineeringLog(workspace);
  await expect(log).toContainText(`[RESULT] PASS · Batch ${sent.batchId}`, { timeout: 30_000 });
  for (let siteId = 1; siteId <= managed.ppuASites; siteId += 1) {
    const result = engineeringSiteRow(workspace, siteId).locator(".engineeringResult");
    if (selectedSites.includes(siteId)) await expect(result).toHaveText("PASS", { timeout: 30_000 });
    else await expect(result).not.toHaveText("PASS");
  }
  expect(traffic.batches).toHaveLength(1);
  expect(traffic.legacy).toEqual([]);
});

// Carried over from the retired PPU runtime_acceptance `eight-site-batch`
// scenario (#1550): every Site of one PPU in ONE Manager Batch, one Image, one
// Job per Site, no retry, each Job bound to that Image.
test("EMode Manager Batch programs every Site of one PPU with one Image, one Job per Site and no retry", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  const workspace = await openEngineering(page, managed.ppuA);
  const job = await selectEngineeringIc(page);
  const allSites = Array.from({ length: managed.ppuASites }, (_, index) => index + 1);
  const image = imagePattern(512, 41, 9);
  await setEngineeringSites(workspace, allSites, managed.ppuASites);
  await setEngineeringOperations(job, ["program"]);
  await job.getByLabel("Engineering Programming Image file").setInputFiles(imageFile("engineering-all-sites.bin", image));
  await job.getByRole("button", { name: /START PROGRAMMING/ }).click();
  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(1);
  const sent = traffic.batches[0];
  expect(sent.body.targets).toEqual([{ ppu_alias: managed.ppuA, site_ids: allSites }]);
  await expect.poll(() => sent.batchId, { timeout: 15_000 }).toMatch(/^[0-9a-f]{32}$/);

  const batch = await settledManagerBatch(request, sent.batchId!, 90_000);
  expect(batch.outcome).toBe("PASS");
  expect(batch.counts).toMatchObject({ sites: allSites.length, pass: allSites.length, fail: 0 });
  expect(batch.attempts).toHaveLength(allSites.length);
  const runs = await batchRuns(request, batch);
  expect(runs.map(item => item.run.site_id).sort((a, b) => a - b)).toEqual(allSites);
  const imageSha = createHash("sha256").update(image).digest("hex");
  for (const { run } of runs) {
    expect(run.outcome).toBe("PASS");
    expect(run.receipt?.observed_image_sha256).toBe(imageSha);
  }
  expect(new Set(runs.map(item => item.run.receipt?.job_id)).size).toBe(allSites.length);
  expect(traffic.legacy).toEqual([]);
});
