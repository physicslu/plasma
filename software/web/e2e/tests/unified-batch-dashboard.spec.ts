import { expect, test, type Page, type Route } from "@playwright/test";
import { expandProductionTree } from "./production-console-helpers";

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
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.route("**/api/devices/search**", async route => {
    const query = new URL(route.request().url()).searchParams.get("q") ?? "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        rest_contract_version: "3",
        query,
        catalog_size: 7657,
        count: 1,
        results: [{
          vendor: "STMicroelectronics",
          family: "STM32F1",
          subfamily: null,
          plasma_series: "STM32",
          identifier: "STM32F103C8T6",
          identifier_kind: "manufacturer_part_number",
          icpn: "STM32F103C8T6",
          package: null,
          cpu_architectures: ["ARM Cortex-M3"],
          backend: { type: "openocd", distribution: "upstream-openocd", target_config: "tcl/target/stm32f1x.cfg", mapping_status: "mapping_candidate" },
          physical_validation: { engineering_status: "not_verified", ppu_status: "no_evidence", socket_status: "no_evidence" },
          catalog_origin: "test",
        }],
      }),
    });
  });
}

async function batchSummaryComputedStyle(page: Page, ariaLabel: string) {
  const summary = page.getByRole("region", { name: ariaLabel });
  await expect(summary).toBeVisible();
  return await summary.evaluate(element => {
    const pass = element.querySelector<HTMLElement>('[data-kpi="pass"]')!;
    const fail = element.querySelector<HTMLElement>('[data-kpi="fail"]')!;
    const passLabel = pass.querySelector<HTMLElement>("small")!;
    const passValue = pass.querySelector<HTMLElement>("b")!;
    const failLabel = fail.querySelector<HTMLElement>("small")!;
    const failValue = fail.querySelector<HTMLElement>("b")!;
    const summaryStyle = getComputedStyle(element);
    const passStyle = getComputedStyle(pass);
    const failStyle = getComputedStyle(fail);
    const passLabelStyle = getComputedStyle(passLabel);
    const passValueStyle = getComputedStyle(passValue);
    const failLabelStyle = getComputedStyle(failLabel);
    const failValueStyle = getComputedStyle(failValue);
    return {
      fontFamily: summaryStyle.fontFamily,
      pass: {
        background: passStyle.backgroundColor,
        edgeColor: passStyle.borderLeftColor,
        edgeWidth: passStyle.borderLeftWidth,
        minHeight: passStyle.minHeight,
        paddingTop: passStyle.paddingTop,
        paddingLeft: passStyle.paddingLeft,
        labelSize: passLabelStyle.fontSize,
        labelWeight: passLabelStyle.fontWeight,
        valueSize: passValueStyle.fontSize,
        valueWeight: passValueStyle.fontWeight,
      },
      fail: {
        background: failStyle.backgroundColor,
        edgeColor: failStyle.borderLeftColor,
        edgeWidth: failStyle.borderLeftWidth,
        minHeight: failStyle.minHeight,
        paddingTop: failStyle.paddingTop,
        paddingLeft: failStyle.paddingLeft,
        labelSize: failLabelStyle.fontSize,
        labelWeight: failLabelStyle.fontWeight,
        valueSize: failValueStyle.fontSize,
        valueWeight: failValueStyle.fontWeight,
      },
    };
  });
}

test("Production Factory Console v2 keeps tree selection, LED status and separate next-Batch membership", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/fleet");

  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  const kpis = page.getByRole("region", { name: "Production Batch Summary" });
  await expect(kpis.getByText("BATCH SUMMARY", { exact: true })).toBeVisible();
  await expect(kpis.locator("article")).toHaveCount(7);
  await expect(kpis.getByText("SITES", { exact: true })).toBeVisible();
  await expect(kpis.getByText("TOTAL IC", { exact: true })).toBeVisible();
  await expect(kpis.getByText("BATCH TIME", { exact: true })).toBeVisible();

  const productionSelection = page.getByRole("region", { name: "PRODUCTION SITE SELECTION" });
  await expect(productionSelection).toBeVisible();
  await expandProductionTree(page);
  const ppu1site1 = page.getByRole("checkbox", { name: "Production Set mock-facility-01 mock-facility-01-ppu-01 SITE-01" });
  const ppu1site2 = page.getByRole("checkbox", { name: "Production Set mock-facility-01 mock-facility-01-ppu-01 SITE-02" });
  await ppu1site1.check();
  await ppu1site2.check();
  await productionSelection.getByRole("button", { name: "SET PRODUCTION SITES" }).click();

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live).toBeVisible();
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
  const dimensions = await live.locator(".factorySiteLedCard").evaluateAll(cards => cards.map(card => {
    const rect = card.getBoundingClientRect();
    return [Math.round(rect.width), Math.round(rect.height)];
  }));
  expect(new Set(dimensions.map(value => value.join("x"))).size).toBe(1);

  const ppuMaster = live.getByRole("checkbox", { name: "Batch select Mock PPU 01", exact: true });
  const site2 = live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02", exact: true });
  await expect(ppuMaster).toBeChecked();
  await site2.uncheck();
  await expect(site2).not.toBeChecked();
  await expect.poll(() => ppuMaster.evaluate((element: HTMLInputElement) => element.indeterminate)).toBe(true);
  await expect(kpis.locator('[data-kpi="total-ic"] b')).toHaveText("1");
  await expect(kpis.locator('[data-kpi="production-sites"] b')).toHaveText("1");

  const hide = productionSelection.getByRole("button", { name: /收起|Hide/ });
  await hide.click();
  await expect(productionSelection.locator(".operatorPanelBody")).toBeHidden();
  await expect(live).toBeVisible();

  await expect(page.getByText("Cancel PPU", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /ABORT/ })).toBeDisabled();
  await expect(page.getByLabel("Site Retry Limit")).toHaveValue("3");
});

test("Engineering Programming remains the status-first single-PPU workspace", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" })).toBeVisible();
  await expect(page.locator(".engineeringProgrammingV2 .targetingCard")).toBeVisible();
  await expect(page.locator(".engineeringProgrammingV2 .programmingJobCard")).toBeVisible();
  await expect(page.locator(".engineeringProgrammingV2 .liveSiteStatus")).toBeVisible();
  await expect(page.getByLabel("Engineering Site selection").locator("tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Select all Engineering batch Sites")).toBeChecked();
  await expect(page.getByLabel("Site Retry Limit")).toHaveValue("3");
});

test("PMode and EMode Batch Summary share identical PASS FAIL computed styles", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/fleet");
  const productionStyle = await batchSummaryComputedStyle(page, "Production Batch Summary");

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  const engineeringStyle = await batchSummaryComputedStyle(page, "Engineering Batch Summary");

  expect(engineeringStyle).toEqual(productionStyle);
  expect(productionStyle.pass.edgeColor).toBe("rgb(21, 128, 61)");
  expect(productionStyle.fail.edgeColor).toBe("rgb(220, 38, 38)");
  expect(productionStyle.pass.edgeWidth).toBe("4px");
  expect(productionStyle.fail.edgeWidth).toBe("4px");
  expect(productionStyle.pass.minHeight).toBe("58px");
  expect(productionStyle.pass.paddingTop).toBe("8px");
  expect(productionStyle.pass.paddingLeft).toBe("10px");
  expect(productionStyle.pass.labelSize).toBe("10px");
  expect(productionStyle.fail.labelSize).toBe("10px");
  expect(productionStyle.pass.labelWeight).toBe("900");
  expect(productionStyle.fail.labelWeight).toBe("900");
  expect(productionStyle.pass.valueSize).toBe("30px");
  expect(productionStyle.fail.valueSize).toBe("30px");
  expect(productionStyle.pass.valueWeight).toBe("900");
  expect(productionStyle.fail.valueWeight).toBe("900");
  expect(productionStyle.pass.background).not.toBe(productionStyle.fail.background);
});
