import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppu1Id = `${facilityId}-ppu-01`;
const ppu2Id = `${facilityId}-ppu-02`;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 2,
    site_count: 6,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [
        { ppu_id: ppu1Id, display_name: "Mock PPU 01", model: "MOCK-PPU", site_count: 2, provider: "mock" },
        { ppu_id: ppu2Id, display_name: "Mock PPU 02", model: "MOCK-PPU", site_count: 4, provider: "mock" },
      ],
    }],
  };
}

function targetStatus(ppuId: string) {
  const siteCount = ppuId === ppu1Id ? 2 : 4;
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: ppuId === ppu1Id ? "Mock PPU 01" : "Mock PPU 02",
      site_count: siteCount,
      enabled_site_count: siteCount,
      capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
    },
    sites: Array.from({ length: siteCount }, (_, index) => ({
      site_id: index + 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

async function installMockProvider(page: Page) {
  let sessionCalls = 0;
  const statusCalls = new Map<string, number>();

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionCalls += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }

    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(url.pathname);
    if (targetMatch && request.method() === "GET") {
      const ppuId = decodeURIComponent(targetMatch[2]);
      statusCalls.set(ppuId, (statusCalls.get(ppuId) ?? 0) + 1);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(ppuId)) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  return {
    sessionCalls: () => sessionCalls,
    statusCalls: (ppuId: string) => statusCalls.get(ppuId) ?? 0,
  };
}

function pmodOperation(page: Page, code: "E" | "P" | "V" | "R") {
  return page.locator(".batchOperations label").filter({ hasText: code }).getByRole("checkbox");
}

test("Pmod and Emode keep configuration while runtime is re-read from the backend", async ({ page }) => {
  const runtime = await installMockProvider(page);

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await page.getByRole("checkbox", { name: `${facilityId} ${ppu1Id} SITE-01` }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppu1Id}"]`)).toBeVisible();

  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "shared-mode-state.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([1, 2, 3, 4, 5, 6, 7, 8]),
  });
  await pmodOperation(page, "P").check();
  await pmodOperation(page, "R").check();
  await page.getByRole("button", { name: "收起選擇器", exact: true }).click();
  await expect(page.locator(".productionWorkspace")).toHaveClass(/selector-collapsed/);

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Engineering Mode" })).toBeVisible();
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".engineeringProgramming .programmingFileName")).toHaveText("shared-mode-state.bin");

  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(ppu).toBeVisible();
  await ppu.selectOption(ppu2Id);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(4, { timeout: 15_000 });
  await page.getByRole("checkbox", { name: "選取 SITE 2" }).uncheck();
  await page.getByLabel("Engineering batch erase").check();
  await page.getByLabel("Engineering batch read").check();
  await page.getByLabel("Engineering READ offset").fill("32");
  await page.getByLabel("Engineering READ length").fill("128");

  await page.getByRole("link", { name: "量產模式", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppu1Id}"]`)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".productionWorkspace")).toHaveClass(/selector-collapsed/);
  await expect(page.locator(".productionBatchToolbar .programmingFileName")).toHaveText("shared-mode-state.bin");
  await expect(pmodOperation(page, "P")).toBeChecked();
  await expect(pmodOperation(page, "R")).toBeChecked();
  await expect(pmodOperation(page, "E")).not.toBeChecked();
  await expect(pmodOperation(page, "V")).not.toBeChecked();

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  await expect(page.getByRole("button", { name: "Programming", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".engineeringProgramming .programmingFileName")).toHaveText("shared-mode-state.bin");
  await expect(page.getByLabel("Engineering PPU", { exact: true })).toHaveValue(ppu2Id);
  await expect(page.getByRole("checkbox", { name: "選取 SITE 2" })).not.toBeChecked();
  await expect(page.getByLabel("Engineering batch erase")).toBeChecked();
  await expect(page.getByLabel("Engineering batch read")).toBeChecked();
  await expect(page.getByLabel("Engineering READ offset")).toHaveValue("32");
  await expect(page.getByLabel("Engineering READ length")).toHaveValue("128");

  expect(runtime.sessionCalls()).toBe(1);
  expect(runtime.statusCalls(ppu1Id)).toBeGreaterThanOrEqual(2);
});
