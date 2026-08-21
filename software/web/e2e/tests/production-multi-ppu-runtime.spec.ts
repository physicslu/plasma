import { expect, test, type Page, type Request } from "@playwright/test";

const facilityId = process.env.MOCK_CD_PRODUCTION_FACILITY_ID ?? "mock-facility-01";
const ppuOne = process.env.MOCK_CD_PRODUCTION_PPU_ONE ?? `${facilityId}-ppu-01`;
const ppuTwo = process.env.MOCK_CD_PRODUCTION_PPU_TWO ?? `${facilityId}-ppu-02`;
const browserJobPath = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/jobs$/;

function ppuCard(page: Page, ppuId: string) {
  return page.locator(`[data-production-target="${facilityId}::${ppuId}"]`);
}

function siteCard(page: Page, ppuId: string, siteId = 1) {
  return ppuCard(page, ppuId).locator(`[data-production-site="${siteId}"]`);
}

function fpsCheckbox(page: Page, ppuId: string, siteId = 1) {
  return page.getByRole("checkbox", {
    name: `${facilityId} ${ppuId} SITE-${String(siteId).padStart(2, "0")}`,
  });
}

async function openTwoPpuProductionSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  const topology = page.getByRole("region", { name: "Mock topology summary" });
  await expect(topology).toContainText("3");
  await expect(topology).toContainText("12");
  await expect(fpsCheckbox(page, ppuOne)).toBeVisible();
  await expect(fpsCheckbox(page, ppuTwo)).toBeVisible();

  await fpsCheckbox(page, ppuOne).check();
  await fpsCheckbox(page, ppuTwo).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();

  const first = ppuCard(page, ppuOne);
  const second = ppuCard(page, ppuTwo);
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();

  const erase = page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox");
  await erase.check();
  return { first, second };
}

function observeBrowserOwnership(page: Page) {
  const batchBodies: Array<Record<string, unknown>> = [];
  const batchPpuCancels: string[] = [];
  let browserJobPosts = 0;
  page.on("request", (request: Request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (url.pathname === "/api/batches") {
      batchBodies.push(request.postDataJSON() as Record<string, unknown>);
      return;
    }
    if (browserJobPath.test(url.pathname)) {
      browserJobPosts += 1;
      return;
    }
    const ppuCancel = /^\/api\/batches\/[^/]+\/targets\/([^/]+)\/([^/]+)\/cancel$/.exec(url.pathname);
    if (ppuCancel) batchPpuCancels.push(decodeURIComponent(ppuCancel[2]));
  });
  return {
    batchBodies,
    batchPpuCancels,
    browserJobPosts: () => browserJobPosts,
  };
}

test("real Production Mock submits one server Batch for two PPUs and completes both", async ({ page }) => {
  const ownership = observeBrowserOwnership(page);
  const { first, second } = await openTwoPpuProductionSet(page);

  await page.locator(".executeBatchButton").click();

  await expect.poll(() => ownership.batchBodies.length, { timeout: 5_000 }).toBe(1);
  const body = ownership.batchBodies[0] as {
    targets?: Array<{ ppu_id?: string }>;
    execution_policy?: Record<string, unknown>;
  };
  expect(body.targets?.map(target => target.ppu_id)).toEqual([ppuOne, ppuTwo]);
  expect(body.execution_policy).toEqual({
    repeat_count: 1,
    site_retry_limit: 0,
    failed_site_stop_threshold: null,
  });
  expect(ownership.browserJobPosts()).toBe(0);

  await expect(first.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
  await expect(second.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(page.locator(".serverBatchStatistics")).toHaveAttribute("data-batch-state", "success");
  expect(ownership.browserJobPosts()).toBe(0);
});

test("real Production Mock shares one Programming Asset across two PPUs for Erase Program Verify", async ({ page }) => {
  const ownership = observeBrowserOwnership(page);
  await openTwoPpuProductionSet(page);

  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "production-shared-asset.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(4096, 0xa5),
  });
  await page.locator(".batchOperations label").filter({ hasText: "P" }).getByRole("checkbox").check();
  await page.locator(".batchOperations label").filter({ hasText: "V" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();

  await expect.poll(() => ownership.batchBodies.length, { timeout: 5_000 }).toBe(1);
  const body = ownership.batchBodies[0] as {
    targets?: Array<{ ppu_id?: string }>;
    operations?: string[];
    asset?: {
      asset_name?: string;
      asset_size?: number;
      asset_sha256?: string;
      asset_base64?: string;
    };
  };
  expect(body.targets?.map(target => target.ppu_id)).toEqual([ppuOne, ppuTwo]);
  expect(body.operations).toEqual(["erase", "program", "verify"]);
  expect(body.asset?.asset_name).toBe("production-shared-asset.bin");
  expect(body.asset?.asset_size).toBe(4096);
  expect(body.asset?.asset_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(body.asset?.asset_base64).toBeTruthy();
  expect(ownership.browserJobPosts()).toBe(0);

  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "success", { timeout: 30_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 30_000 });
  await expect(page.locator(".serverBatchStatistics")).toHaveAttribute("data-batch-state", "success");
  await expect(page.locator('[data-operation-stat="program"]')).toContainText("Logical 2");
  await expect(page.locator('[data-operation-stat="verify"]')).toContainText("Logical 2");
  expect(ownership.browserJobPosts()).toBe(0);
});

test("real Production Mock cancels one PPU through Batch endpoint without stopping the other", async ({ page }) => {
  const ownership = observeBrowserOwnership(page);
  const { first } = await openTwoPpuProductionSet(page);

  await page.locator(".executeBatchButton").click();
  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

  await first.getByRole("button", { name: "Cancel PPU", exact: true }).click();
  await expect.poll(() => ownership.batchPpuCancels, { timeout: 5_000 }).toContain(ppuOne);
  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "cancelled", { timeout: 10_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(page.locator(".serverBatchStatistics")).toHaveAttribute("data-batch-state", "partial");

  expect(ownership.batchPpuCancels).not.toContain(ppuTwo);
  expect(ownership.browserJobPosts()).toBe(0);
});
