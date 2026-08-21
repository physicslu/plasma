import { expect, test, type Page, type Request } from "@playwright/test";

type StartObservation = {
  ppuId: string;
  siteId: number;
  operation: string;
  observedAtMs: number;
};

const facilityId = process.env.MOCK_CD_PRODUCTION_FACILITY_ID ?? "mock-facility-01";
const ppuOne = process.env.MOCK_CD_PRODUCTION_PPU_ONE ?? `${facilityId}-ppu-01`;
const ppuTwo = process.env.MOCK_CD_PRODUCTION_PPU_TWO ?? `${facilityId}-ppu-02`;
const targetJobPath = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/jobs$/;

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
  await expect(topology).toContainText("60");

  await fpsCheckbox(page, ppuOne).check();
  await fpsCheckbox(page, ppuTwo).check();
  await page.getByRole("button", { name: "套用 FPS", exact: true }).click();

  const first = ppuCard(page, ppuOne);
  const second = ppuCard(page, ppuTwo);
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();

  const erase = page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox");
  await erase.check();
  return { first, second };
}

function observeStarts(page: Page, starts: StartObservation[]) {
  page.on("request", (request: Request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    const match = targetJobPath.exec(url.pathname);
    if (!match) return;
    const body = request.postDataJSON() as { site_id?: number; operation?: string };
    if (typeof body.site_id !== "number" || typeof body.operation !== "string") return;
    starts.push({
      ppuId: decodeURIComponent(match[2]),
      siteId: body.site_id,
      operation: body.operation,
      observedAtMs: Date.now(),
    });
  });
}

test("real Production Mock starts two different PPUs concurrently and completes both", async ({ page }) => {
  const starts: StartObservation[] = [];
  observeStarts(page, starts);
  const { first, second } = await openTwoPpuProductionSet(page);

  await page.locator(".executeBatchButton").click();

  await expect(first.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
  await expect(second.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

  await expect.poll(() => new Set(starts.map(item => item.ppuId)).size, { timeout: 5_000 }).toBe(2);
  const firstStartByPpu = new Map<string, number>();
  for (const item of starts) {
    if (!firstStartByPpu.has(item.ppuId)) firstStartByPpu.set(item.ppuId, item.observedAtMs);
  }
  expect(firstStartByPpu.has(ppuOne)).toBe(true);
  expect(firstStartByPpu.has(ppuTwo)).toBe(true);
  expect(Math.abs((firstStartByPpu.get(ppuOne) ?? 0) - (firstStartByPpu.get(ppuTwo) ?? 0))).toBeLessThan(1_500);

  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(page.locator(".batchState")).toContainText("COMPLETE");
  await expect(page.locator(".productionPrototypeLog")).toContainText("[BAT] COMPLETE");
});

test("real Production Mock cancels one PPU without stopping the other", async ({ page }) => {
  const starts: StartObservation[] = [];
  observeStarts(page, starts);
  const { first, second } = await openTwoPpuProductionSet(page);

  await page.locator(".executeBatchButton").click();
  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

  await first.getByRole("button", { name: "Cancel PPU", exact: true }).click();
  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "cancelled", { timeout: 10_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(page.locator(".batchState")).toContainText("PARTIAL");

  const log = page.locator(".productionPrototypeLog");
  await expect(log).toContainText(`[PPU] CANCEL REQUESTED · ${facilityId}::${ppuOne}`);
  await expect(log).toContainText("[BAT] PARTIAL");
  await expect(log).not.toContainText(`[PPU] CANCEL REQUESTED · ${facilityId}::${ppuTwo}`);
});
