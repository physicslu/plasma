import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

type Operation = "erase" | "program" | "verify" | "read";

type StartRequest = {
  siteId: number;
  operation: Operation;
};

type BatchRequest = {
  targets?: Array<{ facility_id?: string; ppu_id?: string; site_ids?: number[] }>;
  operations?: Operation[];
};

const gatewayUrl = process.env.MOCK_CD_GATEWAY_URL ?? "http://127.0.0.1:19801";
const unreachableGatewayUrl = process.env.MOCK_CD_UNREACHABLE_GATEWAY_URL ?? "http://127.0.0.1:19899";
const engineeringFacilityId = process.env.MOCK_CD_ENGINEERING_FACILITY_ID ?? "mock-facility-02";
const engineeringPpuId = process.env.MOCK_CD_ENGINEERING_PPU_ID ?? "mock-facility-02-ppu-03";
const engineeringPpuSites = Number(process.env.MOCK_CD_ENGINEERING_PPU_SITES ?? "6");
const engineeringMainFlashBytes = 4 * 1024 * 1024;
const imageAssetBytes = Buffer.from(Array.from({ length: 256 }, (_, index) => (index * 17 + 3) & 0xff));
const operationLabels: Record<Operation, string> = {
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  read: "讀取",
};
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];

const engineeringLog = (page: Page) => page.getByLabel("Engineering job log");
const engineeringRow = (page: Page, siteId: number) => {
  const label = `SITE-${String(siteId).padStart(2, "0")}`;
  return page.locator(".channelTable tbody tr").filter({ hasText: label }).first();
};

async function openEngineeringProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(8, { timeout: 15_000 });
  await expect(page.locator(".topologyFoot")).toContainText("System Topology: 8 Facilities | 32 PPUs | 160 Sites");

  await facility.selectOption(engineeringFacilityId);
  await ppu.selectOption(engineeringPpuId);
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText(engineeringPpuId);
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText(`${engineeringPpuSites} Sites`);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites, { timeout: 15_000 });
  await expect(page.getByText("SITE-00", { exact: true })).toHaveCount(0);
}

async function setEngineeringBatchSites(page: Page, siteIds: number[]) {
  const desired = new Set(siteIds);
  for (let siteId = 1; siteId <= engineeringPpuSites; siteId += 1) {
    const checkbox = page.getByLabel(`Batch select SITE ${siteId}`);
    const checked = await checkbox.isChecked();
    if (desired.has(siteId) && !checked) await checkbox.check();
    if (!desired.has(siteId) && checked) await checkbox.uncheck();
  }
}

async function setEngineeringBatchOperations(page: Page, operations: Operation[]) {
  const desired = new Set(operations);
  for (const operation of operationOrder) {
    const checkbox = page.getByLabel(`Engineering batch ${operation}`);
    const checked = await checkbox.isChecked();
    if (desired.has(operation) && !checked) await checkbox.check();
    if (!desired.has(operation) && checked) await checkbox.uncheck();
  }
}

test("Control Station root and retired /ppu route never expose the legacy Site Matrix", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByText("選擇產品模式", { exact: true })).toBeVisible();
  await expect(page.getByText("SITE MATRIX", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PPU CONTROL", { exact: true })).toHaveCount(0);

  await page.goto("/ppu");
  await expect(page).toHaveURL(/\/engineering$/);
  await expect(page.getByRole("button", { name: "Programming", exact: true })).toBeVisible();
  await expect(page.getByText("SITE MATRIX", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PPU CONTROL", { exact: true })).toHaveCount(0);
});

test("Engineering Gateway reports offline and recovers without reviving direct PPU Console ownership", async ({ page }) => {
  await openEngineeringProgramming(page);

  const gatewayInput = page.getByLabel("Engineering Gateway URL");
  const gatewayForm = page.locator(".engineeringGateway");
  await expect(gatewayForm).toHaveClass(/online/);

  await gatewayInput.fill(unreachableGatewayUrl);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(gatewayForm).toHaveClass(/offline/, { timeout: 15_000 });
  await expect(engineeringLog(page)).toContainText(unreachableGatewayUrl, { timeout: 15_000 });

  await gatewayInput.fill(gatewayUrl);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(gatewayForm).toHaveClass(/online/, { timeout: 15_000 });
  await expect(page.getByLabel("Engineering Facility", { exact: true }).locator("option")).toHaveCount(8, { timeout: 15_000 });

  const malformed = "ftp://invalid-gateway.local";
  await gatewayInput.fill(malformed);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(engineeringLog(page)).toContainText(malformed);
  await expect(gatewayForm).toHaveClass(/online/);
});

test("EMode owns real per-Site E/P/V/R and Read download through the Python Engineering provider", async ({ page }) => {
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

  await openEngineeringProgramming(page);
  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "engineering-provider-runtime.bin",
    mimeType: "application/octet-stream",
    buffer: imageAssetBytes,
  });

  const siteId = engineeringPpuSites;
  const row = engineeringRow(page, siteId);
  for (const operation of operationOrder) {
    await test.step(`${engineeringFacilityId}/${engineeringPpuId}/SITE-${siteId}: ${operation}`, async () => {
      const before = engineeringStarts.length;
      await page.getByLabel(`SITE ${siteId} ${operationLabels[operation]}`).click();
      await expect.poll(() => engineeringStarts.length, { timeout: 15_000 }).toBe(before + 1);
      expect(engineeringStarts[before]).toEqual({ siteId, operation });
      await expect(row.locator(".state")).toHaveText("SUCCESS", { timeout: 30_000 });
    });
  }

  const downloadLink = page.getByLabel(`Download SITE ${siteId} read file`);
  await expect(downloadLink).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    downloadLink.click(),
  ]);
  expect(download.suggestedFilename()).toBe(`read_SITE${siteId}_main_flash.bin`);
  const path = await download.path();
  if (!path) throw new Error("Engineering Mock PPU Read did not produce a local file");
  const bytes = await readFile(path);
  expect(bytes.length).toBe(engineeringMainFlashBytes);
  expect(bytes.subarray(0, imageAssetBytes.length).equals(imageAssetBytes)).toBe(true);
  expect(bytes.subarray(imageAssetBytes.length).every(value => value === 0xff)).toBe(true);
});

test("EMode server-owned Batch carries selected Sites and operations", async ({ page }) => {
  const batches: BatchRequest[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "POST" || url.pathname !== "/api/batches") return;
    batches.push(request.postDataJSON() as BatchRequest);
  });

  await openEngineeringProgramming(page);
  const selectedSites = engineeringPpuSites >= 3 ? [1, 3, engineeringPpuSites] : [1, engineeringPpuSites];
  const operations: Operation[] = ["erase", "read"];
  await setEngineeringBatchSites(page, selectedSites);
  await setEngineeringBatchOperations(page, operations);

  const start = page.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(start).toBeEnabled();
  await start.click();
  await expect.poll(() => batches.length, { timeout: 15_000 }).toBe(1);

  expect(batches[0]?.targets).toEqual([{
    facility_id: engineeringFacilityId,
    ppu_id: engineeringPpuId,
    site_ids: selectedSites,
  }]);
  expect(batches[0]?.operations).toEqual(operations);

  await expect(engineeringLog(page)).toContainText("[BATCH] SUCCESS", { timeout: 30_000 });
  for (const siteId of selectedSites) {
    await expect(engineeringRow(page, siteId).locator(".engineeringResult")).toHaveText("PASS", { timeout: 30_000 });
  }
});
