import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

type Operation = "erase" | "program" | "verify" | "read";

type StartRequest = {
  siteId: number;
  operation: Operation;
};

const gatewayUrl = process.env.MOCK_CD_GATEWAY_URL ?? "http://127.0.0.1:19801";
const unreachableGatewayUrl = process.env.MOCK_CD_UNREACHABLE_GATEWAY_URL ?? "http://127.0.0.1:19899";
const expectedSites = Number(process.env.MOCK_CD_EXPECTED_SITES ?? "8");
const expectedPpuId = process.env.MOCK_CD_EXPECTED_PPU_ID ?? "mock-ppu-a";
const engineeringFacilityId = process.env.MOCK_CD_ENGINEERING_FACILITY_ID ?? "mock-facility-02";
const engineeringPpuId = process.env.MOCK_CD_ENGINEERING_PPU_ID ?? "mock-facility-02-ppu-03";
const engineeringPpuSites = Number(process.env.MOCK_CD_ENGINEERING_PPU_SITES ?? "6");
const firmware = Buffer.from(Array.from({ length: 256 }, (_, index) => (index * 17 + 3) & 0xff));
const operationLabels: Record<Operation, string> = {
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  read: "讀取",
};
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];

const liveLog = (page: Page) => page.getByLabel("Live job log");
const siteRow = (page: Page, siteId: number) => page.locator(".channelTable tbody tr").filter({ hasText: `SITE ${siteId}` }).first();
const allSiteIds = () => Array.from({ length: expectedSites }, (_, index) => index + 1);

function representativeSelections(siteCount: number): number[][] {
  if (!Number.isInteger(siteCount) || siteCount < 1) {
    throw new Error(`invalid Site count for Browser Runtime Acceptance: ${siteCount}`);
  }
  const all = Array.from({ length: siteCount }, (_, index) => index + 1);
  const candidates: number[][] = [[1]];
  if (siteCount >= 2) candidates.push([1, siteCount]);
  if (siteCount >= 3) {
    const interior = Math.max(2, Math.min(siteCount - 1, Math.floor(siteCount / 2) + 1));
    candidates.push([1, interior, siteCount]);
  }
  if (siteCount >= 2) candidates.push(all.slice(0, -1));
  candidates.push(all);

  const seen = new Set<string>();
  return candidates.filter(selection => {
    const key = selection.join(",");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function openRuntimeConsole(page: Page) {
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".gatewayHealth")).toContainText(`${expectedSites}/${expectedSites} Enabled`);
  await expect(page.getByLabel("PPU identity")).toContainText(expectedPpuId);
  await expect(page.locator(".channelDetails")).toHaveCount(expectedSites);
}

async function runSiteOperation(page: Page, siteId: number, operation: Operation) {
  const label = operationLabels[operation];
  const row = siteRow(page, siteId);
  const accepted = liveLog(page).locator("span")
    .filter({ hasText: `[SITE ${siteId}]` })
    .filter({ hasText: "accepted by Plasma" })
    .filter({ hasText: `· ${operation.toUpperCase()}` });
  const before = await accepted.count();

  await page.getByLabel(`SITE ${siteId} ${label}`).click();
  await expect.poll(() => accepted.count(), { timeout: 15_000 }).toBe(before + 1);
  await expect(row.locator("td").nth(2)).toContainText(label);
  await expect(row.locator(".state")).toHaveText("成功", { timeout: 15_000 });
}

async function setSelectedSites(page: Page, selectedSites: number[]) {
  const desired = new Set(selectedSites);
  if (desired.size === 0) throw new Error("Browser Runtime Acceptance does not permit an empty Site selection");

  for (const siteId of selectedSites) {
    const checkbox = page.getByLabel(`顯示 SITE ${siteId}`);
    if (!(await checkbox.isChecked())) await checkbox.check();
  }
  for (const siteId of allSiteIds()) {
    if (desired.has(siteId)) continue;
    const checkbox = page.getByLabel(`顯示 SITE ${siteId}`);
    if (await checkbox.isChecked()) await checkbox.uncheck();
  }

  await expect(page.getByLabel("Site 配置摘要")).toContainText(`顯示 ${selectedSites.length} / ${expectedSites}`);
  await expect(page.locator(".batchInfo")).toContainText(
    `目標：${selectedSites.map(siteId => `SITE ${siteId}`).join("、")}`,
  );
}

async function setBatchOperations(page: Page, operations: Operation[]) {
  const desired = new Set(operations);
  for (const operation of operationOrder) {
    const checkbox = page.getByLabel(`批次操作：${operationLabels[operation]}`);
    const checked = await checkbox.isChecked();
    if (desired.has(operation) && !checked) await checkbox.check();
    if (!desired.has(operation) && checked) await checkbox.uncheck();
  }
}

async function runBatchAndAssert(
  page: Page,
  starts: StartRequest[],
  selectedSites: number[],
  operations: Operation[],
) {
  await setSelectedSites(page, selectedSites);
  await setBatchOperations(page, operations);

  const executeName = `批次執行：${operations.map(operation => operationLabels[operation]).join("、")}`;
  const execute = page.getByRole("button", { name: executeName });
  await expect(execute).toBeEnabled();

  const before = starts.length;
  await execute.click();
  await expect.poll(() => starts.length, { timeout: 30_000 }).toBe(before + selectedSites.length * operations.length);

  // The UI intentionally keeps a bounded rolling log. Do not count historical
  // COMPLETE lines because earlier batches can be evicted. Prove that this
  // specific batch terminated and emitted its own completion summary instead.
  await expect(execute).toBeEnabled({ timeout: 30_000 });
  const expectedSummary = `[BATCH] COMPLETE · success: ${selectedSites.map(siteId => `SITE ${siteId}`).join(", ")}`;
  await expect(liveLog(page)).toContainText(expectedSummary, { timeout: 30_000 });

  const actual = starts.slice(before)
    .map(item => `${item.siteId}:${item.operation}`)
    .sort();
  const expected = selectedSites
    .flatMap(siteId => operations.map(operation => `${siteId}:${operation}`))
    .sort();
  expect(actual).toEqual(expected);
  expect(new Set(starts.slice(before).map(item => item.siteId))).toEqual(new Set(selectedSites));
}

test("real Gateway reports offline and recovers cleanly", async ({ page }) => {
  await openRuntimeConsole(page);

  const gatewayInput = page.getByLabel("Plasma Web REST Gateway URL");
  const connected = liveLog(page).locator("span")
    .filter({ hasText: "Plasma Web REST Gateway connected" })
    .filter({ hasText: gatewayUrl });
  await expect(connected).toHaveCount(1);

  await gatewayInput.fill(unreachableGatewayUrl);
  await page.getByRole("button", { name: "連線" }).click();
  await expect(page.locator(".gatewayHealth")).toContainText("Offline", { timeout: 15_000 });

  const offline = liveLog(page).locator("span")
    .filter({ hasText: "Plasma Web REST Gateway offline" })
    .filter({ hasText: unreachableGatewayUrl });
  await expect(offline).toHaveCount(1);
  await expect(offline).toHaveAttribute("data-level", "error");

  await gatewayInput.fill(gatewayUrl);
  await page.getByRole("button", { name: "連線" }).click();
  await expect(page.locator(".gatewayHealth")).toContainText("Online", { timeout: 15_000 });
  await expect(connected).toHaveCount(2);
  await expect(offline).toHaveCount(1);

  const malformed = "ftp://invalid-gateway.local";
  await gatewayInput.fill(malformed);
  await page.getByRole("button", { name: "連線" }).click();
  const rejected = liveLog(page).locator("span")
    .filter({ hasText: "Plasma Web REST Gateway rejected" })
    .filter({ hasText: malformed });
  await expect(rejected).toHaveCount(1);
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
});

test("every enabled Site runs Erase Program Verify Read and downloads exact bytes", async ({ page }) => {
  const starts: StartRequest[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "POST" || url.pathname !== "/api/jobs") return;
    const body = request.postDataJSON() as { site_id?: number; operation?: Operation };
    if (typeof body.site_id === "number" && body.operation) {
      starts.push({ siteId: body.site_id, operation: body.operation });
    }
  });

  await openRuntimeConsole(page);

  await page.getByLabel("選擇 Firmware 檔案").setInputFiles({
    name: "mock-cd-runtime.bin",
    mimeType: "application/octet-stream",
    buffer: firmware,
  });
  await page.getByLabel("READ logical flash offset").fill("0");
  await page.getByLabel("READ byte length").fill(String(firmware.length));

  for (let siteId = 1; siteId <= expectedSites; siteId += 1) {
    await test.step(`SITE ${siteId}: Erase -> Program -> Verify -> Read -> download`, async () => {
      for (const operation of operationOrder) {
        const before = starts.length;
        await runSiteOperation(page, siteId, operation);
        await expect.poll(() => starts.length).toBe(before + 1);
        expect(starts[before]).toEqual({ siteId, operation });
      }

      const downloadLink = page.getByLabel(`下載 SITE ${siteId} 讀取檔案`);
      await expect(downloadLink).toBeVisible();
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        downloadLink.click(),
      ]);
      expect(download.suggestedFilename()).toBe(`read_SITE${siteId}_flash.bin`);
      const path = await download.path();
      if (!path) throw new Error(`SITE ${siteId} Read download did not produce a local file`);
      const bytes = await readFile(path);
      expect(bytes.length).toBe(firmware.length);
      expect(bytes.equals(firmware)).toBe(true);
    });
  }
});

test("batch membership supports representative arbitrary Site subsets and selected operations", async ({ page }) => {
  const starts: StartRequest[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "POST" || url.pathname !== "/api/jobs") return;
    const body = request.postDataJSON() as { site_id?: number; operation?: Operation };
    if (typeof body.site_id === "number" && body.operation) {
      starts.push({ siteId: body.site_id, operation: body.operation });
    }
  });

  await openRuntimeConsole(page);

  for (let siteId = 1; siteId <= expectedSites; siteId += 1) {
    await test.step(`SITE ${siteId} batch membership toggles cleanly`, async () => {
      const checkbox = page.getByLabel(`顯示 SITE ${siteId}`);
      await expect(checkbox).toBeChecked();
      await checkbox.uncheck();
      await expect(checkbox).not.toBeChecked();
      await checkbox.check();
      await expect(checkbox).toBeChecked();
    });
  }

  const selections = representativeSelections(expectedSites);
  for (const [index, selection] of selections.entries()) {
    const operations: Operation[] = index === 2 || index === selections.length - 1
      ? ["erase", "read"]
      : index === 1
        ? ["read"]
        : ["erase"];
    await test.step(
      `batch subset ${selection.join(",")} x ${operations.join(",")}`,
      () => runBatchAndAssert(page, starts, selection, operations),
    );
  }

  if (expectedSites >= 3) {
    expect(selections).toContainEqual([1, Math.max(2, Math.min(expectedSites - 1, Math.floor(expectedSites / 2) + 1)), expectedSites]);
  }
  expect(selections.at(-1)).toEqual(allSiteIds());
});

test("Engineering selects a server-reported Mock PPU and executes E/P/V/R through Python", async ({ page }) => {
  const engineeringStarts: StartRequest[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    const expectedPath = `/api/engineering/targets/${engineeringFacilityId}/${engineeringPpuId}/api/jobs`;
    if (request.method() !== "POST" || url.pathname !== expectedPath) return;
    const body = request.postDataJSON() as { site_id?: number; operation?: Operation };
    if (typeof body.site_id === "number" && body.operation) {
      engineeringStarts.push({ siteId: body.site_id, operation: body.operation });
    }
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const facility = page.getByLabel("Engineering Facility");
  const ppu = page.getByLabel("Engineering PPU");
  await expect(facility.locator("option")).toHaveCount(3, { timeout: 15_000 });
  await expect(page.getByText("SERVER SOURCE OF TRUTH")).toContainText("3 Facilities · 12 PPUs · 60 Sites");

  await facility.selectOption(engineeringFacilityId);
  await ppu.selectOption(engineeringPpuId);
  await expect(page.getByLabel("Selected Engineering PPU")).toContainText(engineeringPpuId);
  await expect(page.getByLabel("Selected Engineering PPU")).toContainText(`${engineeringPpuSites} Sites`);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites, { timeout: 15_000 });
  await expect(page.getByText("SITE 0", { exact: true })).toHaveCount(0);

  const siteId = engineeringPpuSites;
  const row = page.locator(".channelTable tbody tr").filter({ hasText: `SITE ${siteId}` }).first();
  await page.getByLabel("Engineering Firmware file").setInputFiles({
    name: "engineering-provider-runtime.bin",
    mimeType: "application/octet-stream",
    buffer: firmware,
  });
  await page.getByLabel("Engineering READ offset").fill("0");
  await page.getByLabel("Engineering READ length").fill(String(firmware.length));

  for (const operation of operationOrder) {
    await test.step(`Engineering ${engineeringFacilityId}/${engineeringPpuId}/SITE ${siteId}: ${operation}`, async () => {
      const before = engineeringStarts.length;
      await page.getByLabel(`SITE ${siteId} ${operationLabels[operation]}`).click();
      await expect.poll(() => engineeringStarts.length, { timeout: 15_000 }).toBe(before + 1);
      expect(engineeringStarts[before]).toEqual({ siteId, operation });
      await expect(row.locator(".state")).toHaveText("SUCCESS", { timeout: 15_000 });
    });
  }

  const downloadLink = page.getByLabel(`Download SITE ${siteId} read file`);
  await expect(downloadLink).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    downloadLink.click(),
  ]);
  expect(download.suggestedFilename()).toBe(`read_SITE${siteId}_flash.bin`);
  const path = await download.path();
  if (!path) throw new Error("Engineering Mock PPU Read did not produce a local file");
  const bytes = await readFile(path);
  expect(bytes.length).toBe(firmware.length);
  expect(bytes.equals(firmware)).toBe(true);
});
