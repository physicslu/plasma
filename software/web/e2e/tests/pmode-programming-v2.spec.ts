import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = "mock-facility-01-ppu-01";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      }],
    }],
  };
}

function status() {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
      site_count: 2,
      enabled_site_count: 2,
      capabilities: { max_supported_sites: 2, operations: ["erase", "program", "verify", "read"] },
    },
    sites: [1, 2].map(siteId => ({
      site_id: siteId,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: null,
    })),
  };
}

async function installApi(page: Page) {
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }
    if (path === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "pmode-programming-v2-session-0000",
            previous_session_cleared: false,
          },
        }),
      });
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
          backend: {
            type: "openocd",
            distribution: "upstream-openocd",
            target_config: "tcl/target/stm32f1x.cfg",
            mapping_status: "mapping_candidate",
          },
          physical_validation: {
            engineering_status: "not_verified",
            ppu_status: "no_evidence",
            socket_status: "no_evidence",
          },
          catalog_origin: "test",
        }],
      }),
    });
  });
}

test("PMode Programming v2 renders the approved single-PPU workflow and direct EPVR", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1369, height: 1149 });
  await page.goto("/fleet/programming");

  await expect(page.getByRole("heading", { name: "SINGLE PPU PROGRAMMING" })).toBeVisible();
  await expect(page.getByText("SYSTEM SETUP & TARGETING", { exact: true })).toBeVisible();
  await expect(page.getByText("PROGRAMMING JOB", { exact: true })).toBeVisible();
  await expect(page.getByText("LIVE SITE STATUS", { exact: true })).toBeVisible();
  await expect(page.getByText("RECENT EVENTS", { exact: true })).toBeVisible();
  await expect(page.getByText("SITE-01", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("SITE-02", { exact: true }).first()).toBeVisible();

  const target = page.getByLabel("Target IC");
  await target.fill("STM32F103C8T6");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await expect(target).toHaveValue("STM32F103C8T6");

  const operationButtons = page.locator(".siteOperationButtons button");
  await expect(operationButtons).toHaveCount(8);
  await expect(page.locator(".siteOperationButtons").first().getByRole("button", { name: "erase SITE-01" })).toHaveText("E");
  await expect(page.locator(".siteOperationButtons").first().getByRole("button", { name: "program SITE-01" })).toHaveText("P");
  await expect(page.locator(".siteOperationButtons").first().getByRole("button", { name: "verify SITE-01" })).toHaveText("V");
  await expect(page.locator(".siteOperationButtons").first().getByRole("button", { name: "read SITE-01" })).toHaveText("R");
});

test("Stop Policy stays compact beside Repeat", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1369, height: 1149 });
  await page.goto("/fleet/programming");

  const repeat = page.getByLabel("Repeat");
  const stop = page.getByLabel("Stop Policy");
  await expect(repeat).toBeVisible();
  await expect(stop).toBeVisible();

  const repeatBox = await repeat.boundingBox();
  const stopBox = await stop.boundingBox();
  expect(repeatBox).not.toBeNull();
  expect(stopBox).not.toBeNull();
  expect(repeatBox!.width).toBeGreaterThanOrEqual(68);
  expect(repeatBox!.width).toBeLessThanOrEqual(78);
  expect(stopBox!.width).toBeGreaterThanOrEqual(112);
  expect(stopBox!.width).toBeLessThanOrEqual(124);
  expect(stopBox!.width).toBeLessThan(160);
});
