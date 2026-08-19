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
const firmware = Buffer.from(Array.from({ length: 256 }, (_, index) => (index * 17 + 3) & 0xff));
const operationLabels: Record<Operation, string> = {
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  read: "讀取",
};

const liveLog = (page: Page) => page.getByLabel("Live job log");
const siteRow = (page: Page, siteId: number) => page.locator(".channelTable tbody tr").filter({ hasText: `SITE ${siteId}` }).first();

async function openRuntimeConsole(page: Page) {
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".gatewayHealth")).toContainText(`${expectedSites}/${expectedSites} Enabled`);
  await expect(page.getByLabel("PPU identity")).toContainText("mock-ppu-a");
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
      await runSiteOperation(page, siteId, "erase");
      await runSiteOperation(page, siteId, "program");
      await runSiteOperation(page, siteId, "verify");
      await runSiteOperation(page, siteId, "read");

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

test("batch membership controls dispatch selected Sites x selected operations", async ({ page }) => {
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

  for (let siteId = 2; siteId <= expectedSites; siteId += 1) {
    await page.getByLabel(`顯示 SITE ${siteId}`).uncheck();
  }
  await expect(page.getByLabel("Site 配置摘要")).toContainText(`顯示 1 / ${expectedSites}`);
  await expect(page.locator(".batchInfo")).toContainText("目標：SITE 1");
  await expect(page.getByLabel("批次執行：尚未選擇操作")).toBeDisabled();

  await page.getByLabel("批次操作：擦除").check();
  const firstExecute = page.getByRole("button", { name: "批次執行：擦除" });
  await expect(firstExecute).toBeEnabled();
  await firstExecute.click();
  await expect.poll(() => starts.length, { timeout: 20_000 }).toBe(1);
  await expect(liveLog(page)).toContainText("[BATCH] COMPLETE", { timeout: 20_000 });
  expect(starts).toEqual([{ siteId: 1, operation: "erase" }]);

  const multiSites = Array.from({ length: expectedSites }, (_, index) => index + 1)
    .filter(siteId => siteId !== 1 && siteId % 2 === 0)
    .slice(0, 3);
  if (multiSites.length === 0) throw new Error("batch membership acceptance requires at least two enabled Sites");
  for (const siteId of multiSites) {
    await page.getByLabel(`顯示 SITE ${siteId}`).check();
  }
  await page.getByLabel("顯示 SITE 1").uncheck();
  await expect(page.getByLabel("Site 配置摘要")).toContainText(`顯示 ${multiSites.length} / ${expectedSites}`);
  await expect(page.locator(".batchInfo")).toContainText(`目標：${multiSites.map(siteId => `SITE ${siteId}`).join("、")}`);

  await page.getByLabel("批次操作：讀取").check();
  const secondExecute = page.getByRole("button", { name: "批次執行：擦除、讀取" });
  await expect(secondExecute).toBeEnabled();
  const beforeSecondBatch = starts.length;
  await secondExecute.click();
  await expect.poll(() => starts.length, { timeout: 30_000 }).toBe(beforeSecondBatch + multiSites.length * 2);
  await expect.poll(
    () => liveLog(page).locator("span").filter({ hasText: "[BATCH] COMPLETE" }).count(),
    { timeout: 30_000 },
  ).toBe(2);

  const actual = starts.slice(beforeSecondBatch)
    .map(item => `${item.siteId}:${item.operation}`)
    .sort();
  const expected = multiSites
    .flatMap(siteId => [`${siteId}:erase`, `${siteId}:read`])
    .sort();
  expect(actual).toEqual(expected);
  expect(new Set(starts.slice(beforeSecondBatch).map(item => item.siteId))).toEqual(new Set(multiSites));
});
