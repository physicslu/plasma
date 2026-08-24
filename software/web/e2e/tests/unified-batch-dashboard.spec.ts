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
  const summary = root.locator(".batchTopologySummary");
  await expect(summary).toBeVisible();
  await expect(root.locator(".unifiedBatchControlStack")).toBeVisible();

  const typography = await summary.evaluate(element => {
    const style = (selector: string) => getComputedStyle(element.querySelector<HTMLElement>(selector)!);
    return {
      contextLabelSize: Number.parseFloat(style(".batchTopologyContext small").fontSize),
      contextValueSize: Number.parseFloat(style(".batchTopologyContext b").fontSize),
      totalLabelSize: Number.parseFloat(style(".batchTopologyTotal small").fontSize),
      totalValueSize: Number.parseFloat(style(".batchTopologyTotal b").fontSize),
      kpiLabelSize: Number.parseFloat(style(".batchTopologyPass small").fontSize),
      kpiValueSize: Number.parseFloat(style(".batchTopologyPass b").fontSize),
      passLabelWeight: Number(style(".batchTopologyPass small").fontWeight),
      passValueWeight: Number(style(".batchTopologyPass b").fontWeight),
      failLabelWeight: Number(style(".batchTopologyFail small").fontWeight),
      failValueWeight: Number(style(".batchTopologyFail b").fontWeight),
      yieldLabelWeight: Number(style(".batchTopologyYield small").fontWeight),
      yieldValueWeight: Number(style(".batchTopologyYield b").fontWeight),
    };
  });
  expect(typography.contextLabelSize).toBeLessThan(typography.kpiLabelSize);
  expect(typography.contextValueSize).toBeLessThan(typography.kpiValueSize);
  expect(typography.kpiLabelSize).toBeGreaterThanOrEqual(12);
  expect(typography.kpiValueSize).toBeGreaterThanOrEqual(34);
  expect(typography.kpiLabelSize).toBeGreaterThan(typography.totalLabelSize);
  expect(typography.kpiValueSize).toBeGreaterThan(typography.totalValueSize);
  for (const weight of [
    typography.passLabelWeight,
    typography.passValueWeight,
    typography.failLabelWeight,
    typography.failValueWeight,
    typography.yieldLabelWeight,
    typography.yieldValueWeight,
  ]) expect(weight).toBeGreaterThanOrEqual(800);

  const active = root.locator(".activeFpsSummary");
  await expect(active).toBeVisible();
  await expect(active.locator("[data-active-fps-state]")).toHaveCount(3);
  await expect(active.locator('[data-active-fps-state="selected"]')).toHaveCount(1);
  await expect(active.locator('[data-active-fps-state="running"]')).toHaveCount(1);
  await expect(active.locator('[data-active-fps-state="terminal"]')).toHaveCount(1);
  await expect(active.locator('[data-active-fps-state="selected"]').getByText("TOTAL SELECTED SITES", { exact: true })).toBeVisible();
  await expect(active.locator('[data-active-fps-state="running"]').getByText("RUNNING SITES", { exact: true })).toBeVisible();
  await expect(active.locator('[data-active-fps-state="terminal"]').getByText("STOPPED SITES", { exact: true })).toBeVisible();

  const policy = root.getByRole("region", { name: "Batch execution policy" });
  const repeatInfo = policy.getByLabel("Repeat policy help");
  await repeatInfo.hover();
  const tooltip = repeatInfo.getByRole("tooltip");
  await expect.poll(() => tooltip.evaluate(element => getComputedStyle(element).opacity)).toBe("1");
  await expect(tooltip).toContainText(/1.*10000/);
  await expect(policy.getByLabel("Site Retry Limit")).toHaveValue("3");

  const visibleLabelDistances = await policy.locator(".batchPolicyField").evaluateAll(fields => fields.map(element => {
    const info = element.querySelector<HTMLElement>(".batchPolicyInfo")!.getBoundingClientRect();
    const input = element.querySelector<HTMLInputElement>("input")!.getBoundingClientRect();
    return Math.max(0, input.left - info.right);
  }));
  expect(visibleLabelDistances).toHaveLength(3);
  for (const distance of visibleLabelDistances) {
    expect(distance).toBeLessThanOrEqual(12);
  }

  const policyInputWidths = await policy.locator(".batchPolicyField input").evaluateAll(inputs =>
    inputs.map(element => element.getBoundingClientRect().width),
  );
  expect(policyInputWidths).toHaveLength(3);
  for (const width of policyInputWidths) {
    expect(width).toBeGreaterThanOrEqual(60);
    expect(width).toBeLessThanOrEqual(100);
  }
  expect(Math.max(...policyInputWidths) - Math.min(...policyInputWidths)).toBeLessThanOrEqual(1);

  const layout = await root.locator(".unifiedBatchControlStack").evaluate(element => {
    const rect = (selector: string) => element.querySelector<HTMLElement>(selector)!.getBoundingClientRect();
    const toolbar = rect(".programmingBatchToolbar");
    const image = rect(".programmingBatchFile");
    const operations = rect(".programmingBatchOperations");
    const actions = rect(".programmingBatchActions");
    const policyRect = rect(".unifiedBatchPolicyPanel");
    return {
      toolbarLeft: toolbar.left,
      toolbarRight: toolbar.right,
      imageLeft: image.left,
      imageRight: image.right,
      imageBottom: image.bottom,
      operationsTop: operations.top,
      operationsBottom: operations.bottom,
      actionsTop: actions.top,
      actionsBottom: actions.bottom,
      policyTop: policyRect.top,
    };
  });

  expect(layout.imageLeft).toBeLessThanOrEqual(layout.toolbarLeft + 12);
  expect(layout.imageRight).toBeGreaterThanOrEqual(layout.toolbarRight - 12);
  expect(layout.imageBottom).toBeLessThanOrEqual(Math.min(layout.operationsTop, layout.actionsTop));
  expect(Math.max(layout.operationsBottom, layout.actionsBottom)).toBeLessThanOrEqual(layout.policyTop);
}

test("Production and Engineering share the compact upper Batch dashboard contract", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await assertDashboardContract(page.locator(".productionMainPanel"));
  const fpsWidth = await page.locator(".fpsSelector").evaluate(element => element.getBoundingClientRect().width);
  expect(fpsWidth).toBeGreaterThanOrEqual(319);
  expect(fpsWidth).toBeLessThanOrEqual(361);
  await expect(page.locator(".productionMainPanel .engineeringBatchDetails")).toBeHidden();

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await assertDashboardContract(page.locator(".engineeringProgramming"));

  const details = page.locator(".engineeringProgramming .engineeringBatchDetails");
  await expect(details).toBeVisible();
  await expect(details).not.toHaveAttribute("open", "");
  await details.locator("summary").click();
  await expect(details).toHaveAttribute("open", "");
  await expect(details.getByText("STATE", { exact: true })).toBeVisible();
  await expect(details.getByText("PASSED SITES", { exact: true })).toBeVisible();
  await expect(details.getByText("FAULTED SITES", { exact: true })).toBeVisible();
  await expect(details.getByText("ERROR SITES", { exact: true })).toBeVisible();
  await expect(details.getByText("CANCELLED SITES", { exact: true })).toBeVisible();
});
