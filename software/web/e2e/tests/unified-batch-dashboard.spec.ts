import { expect, test, type Page, type Route } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: Array.from({ length: 3 }, (_, facilityIndex) => {
      const facilityNumber = facilityIndex + 1;
      const facilityId = `mock-facility-${String(facilityNumber).padStart(2, "0")}`;
      return {
        facility_id: facilityId,
        display_name: `Mock Facility ${String(facilityNumber).padStart(2, "0")}`,
        ppus: siteCounts.map((siteCount, ppuIndex) => ({
          ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
          display_name: `Mock PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
          model: "MOCK-PPU",
          site_count: siteCount,
          provider: "mock",
        })),
      };
    }),
  };
}

function statusFor(facilityId: string, ppuId: string) {
  const ppuNumber = Number(ppuId.slice(-2));
  const siteCount = siteCounts[ppuNumber - 1] ?? 2;
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: `Mock PPU ${String(ppuNumber).padStart(2, "0")}`,
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

async function installDashboardMock(page: Page) {
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "11111111111111111111111111111111",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled dashboard test route" } }),
    });
  });
}

async function assertDashboardContract(root: ReturnType<Page["locator"]>) {
  await expect(root.locator(".batchTopologySummary")).toBeVisible();
  await expect(root.locator(".unifiedBatchControlStack")).toBeVisible();
  const active = root.locator(".activeFpsSummary");
  await expect(active).toBeVisible();
  await expect(active.locator("[data-active-fps-state]")).toHaveCount(7);
  await expect(active.locator('[data-active-fps-state="faulted"]')).toHaveCount(1);
  await expect(active.locator('[data-active-fps-state="error"]')).toHaveCount(1);

  const policy = root.getByRole("region", { name: "Batch execution policy" });
  const repeatInfo = policy.getByLabel("Help for Repeat Count");
  await repeatInfo.hover();
  const tooltip = repeatInfo.getByRole("tooltip");
  await expect.poll(() => tooltip.evaluate(element => getComputedStyle(element).opacity)).toBe("1");
  await expect(tooltip).toContainText(/1.*10000/);

  const distance = await policy.locator(".batchPolicyField").first().evaluate(element => {
    const label = element.querySelector<HTMLElement>(".batchPolicyLabel")!.getBoundingClientRect();
    const input = element.querySelector<HTMLInputElement>("input")!.getBoundingClientRect();
    return Math.max(0, input.left - label.right);
  });
  expect(distance).toBeLessThanOrEqual(12);
}

test("Production and Engineering share the compact upper Batch dashboard contract", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await assertDashboardContract(page.locator(".productionMainPanel"));
  const fpsWidth = await page.locator(".fpsSelector").evaluate(element => element.getBoundingClientRect().width);
  expect(fpsWidth).toBeLessThanOrEqual(300);

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await assertDashboardContract(page.locator(".engineeringProgramming"));
});
