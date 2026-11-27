import { expect, test, type Page } from "@playwright/test";
import { mockFleet, mockManager } from "./managed-programming-helpers";
import { chooseTestTarget, expandProductionTree } from "./production-console-helpers";

// U10: Manager-managed only. Three Facilities × four PPUs (2/4/6/8 Sites)
// from the Mock Manager Registry / Fleet; the device catalog is this spec's own.
async function installDashboardMock(page: Page) {
  await mockManager(page, { ppus: mockFleet() });

  await page.route("**/api/manager/devices/search**", async route => {
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

async function icPickerComputedStyle(page: Page) {
  const picker = page.locator(".icPicker").first();
  await expect(picker).toBeVisible();
  return picker.evaluate(element => {
    const inputShell = element.querySelector<HTMLElement>(".icPickerInput")!;
    const input = inputShell.querySelector<HTMLInputElement>("input")!;
    const pickerStyle = getComputedStyle(element);
    const shellStyle = getComputedStyle(inputShell);
    const inputStyle = getComputedStyle(input);
    return {
      fontFamily: pickerStyle.fontFamily,
      minHeight: shellStyle.minHeight,
      radius: shellStyle.borderRadius,
      inputHeight: inputStyle.height,
      inputSize: inputStyle.fontSize,
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

  const productionSelection = page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" });
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

  const ppuMaster = live.getByRole("checkbox", { name: "Batch select mock-facility-01-ppu-01 · PPU ID mock-facility-01-ppu-01", exact: true });
  const site2 = live.getByRole("checkbox", { name: "Batch select mock-facility-01-ppu-01 · PPU ID mock-facility-01-ppu-01 SITE-02", exact: true });
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
  await expect(page.getByRole("region", { name: "Engineering Programming Job" })).toBeVisible();
  await expect(page.locator(".engineeringProgrammingV2 .liveSiteStatus")).toBeVisible();
  await expect(page.getByLabel("Engineering Site selection").locator("tbody tr")).toHaveCount(2);
  // Managed EMode: no Site is offered before a Target IC is chosen; then the
  // Route-qualified Sites become selectable for the next Batch.
  await expect(page.getByLabel("Select SITE 1 for programming")).toBeDisabled();
  await chooseTestTarget(page, "engineering");
  await expect(page.getByLabel("Select SITE 1 for programming")).toBeEnabled();
  await expect(page.getByLabel("Select SITE 2 for programming")).toBeEnabled();
  // The managed EMode Batch never retries unless the engineer asks for it.
  await expect(page.getByLabel("Site Retry Limit")).toHaveValue("0");
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

test("PMode and EMode share one IC picker style owner while preserving approved density", async ({ page }) => {
  await installDashboardMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/fleet");
  const productionPicker = page.locator(".icPicker").first();
  await expect(productionPicker).toBeVisible();
  await expect(page.locator(".productionIcPicker")).toHaveCount(0);
  const productionStyle = await icPickerComputedStyle(page);

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  const engineeringPicker = page.locator(".engineeringProgrammingV2 .icPicker").first();
  await expect(engineeringPicker).toBeVisible();
  await expect(page.locator(".productionIcPicker")).toHaveCount(0);
  const engineeringStyle = await icPickerComputedStyle(page);

  expect(engineeringStyle.fontFamily).toBe(productionStyle.fontFamily);
  expect(productionStyle).toMatchObject({
    minHeight: "34px",
    radius: "6px",
    inputHeight: "32px",
    inputSize: "10px",
  });
  expect(engineeringStyle).toMatchObject({
    minHeight: "40px",
    radius: "7px",
    inputHeight: "38px",
    inputSize: "12px",
  });
});
