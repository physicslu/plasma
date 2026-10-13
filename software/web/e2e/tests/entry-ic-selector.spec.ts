import { expect, test } from "@playwright/test";

test("entry portal exposes IC lookup as card 03 and global navigation does not duplicate it", async ({ page }) => {
  await page.goto("/demo");

  const productNav = page.getByRole("navigation", { name: "產品模式" });
  await expect(productNav).toBeVisible();
  await expect(productNav.getByRole("link", { name: "IC Selector", exact: true })).toHaveCount(0);
  await expect(page.locator(".globalUtilityNav")).toHaveCount(0);

  const icLookup = page.locator('a.demoCard.utility[href="/devices"]');
  await expect(icLookup).toBeVisible();
  await expect(icLookup.getByText("03", { exact: true })).toBeVisible();
  await expect(icLookup.getByRole("heading", { name: "IC Selector" })).toBeVisible();
  await expect(icLookup.getByText("查詢 IC 料號 →", { exact: true })).toBeVisible();

  await icLookup.click();
  await expect(page).toHaveURL(/\/devices$/);
  await expect(page.getByRole("heading", { name: "IC Selector" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: "IC Selector", exact: true })).toHaveCount(0);

  const theme = page.getByRole("group", { name: "Theme" });
  await expect(theme).toBeVisible();
  await expect(theme.getByRole("button", { name: "Light" })).toBeVisible();
  await expect(theme.getByRole("button", { name: "Dark" })).toBeVisible();
  await theme.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});


test("IC Selector first enriched result renders without page error and pagination reaches later rows", async ({ page }) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", error => pageErrors.push(error));

  const makeResult = (identifier: string, enriched = false) => ({
    vendor: "STMicroelectronics",
    family: "STM32F1",
    subfamily: "STM32F103",
    plasma_series: "STM32F1",
    identifier,
    identifier_kind: "manufacturer_part_number",
    icpn: identifier,
    package: "LQFP",
    pin_count: "48",
    flash_size: "64 KiB",
    temperature_grade: "-40 to 85 C",
    option_suffix: null,
    base_device: "STM32F103C8",
    cpu_architectures: [],
    backend: {
      type: "openocd",
      distribution: "upstream-openocd",
      target_config: "tcl/target/stm32f1x.cfg",
      mapping_status: "mapped",
      mapping_method: "exact",
    },
    catalog_verification: {
      status: "verified_official",
      source_type: "manufacturer",
      source_authority: "STMicroelectronics",
      source_reference: "e2e",
    },
    physical_validation: {
      engineering_status: "no_evidence",
      ppu_status: "no_evidence",
      socket_status: "no_evidence",
    },
    catalog: {
      scope: "production_admitted",
      version: "1.0.0",
      revision_sha256: "a".repeat(64),
    },
    catalog_origin: "e2e",
    backend_candidate: null,
    backend_source_reference: null,
    backend_providers: [],
    manufacturer_device_basic_profile: {
      schema_version: "1.0.0",
      status: "manufacturer_device_basic_available",
      profile_id: "stm32f1-device-basic-v1",
      icpn: identifier,
      manufacturer: "STMicroelectronics",
      family: "STM32F1",
      series: "STM32F103",
      base_device: "STM32F103C8",
      package: "LQFP",
      pin_count: "48",
      flash_size: "64 KiB",
      ram_size: "20 KiB",
      operating_vdd_v: { min: 2, max: 3.6 },
      operating_temperature_c: { min: -40, max: 85 },
      evidence: {
        authority: "STMicroelectronics official",
        source_surface: "st_product_selector",
        selector_url: "https://www.st.com/en/microcontrollers-microprocessors/stm32f103/products.html",
        observed_at_utc: "2026-10-13",
        content_lock: null,
        evidence_strength: "official_product_selector_observation",
      },
      programming_profile_authority: false,
      hardware_runtime_ready: false,
      physical_programming_qualified: false,
    },
    selected_profile: enriched ? {
      schema_version: "1.0.0",
      status: "manufacturer_profile_available",
      icpn: identifier,
      manufacturer_baseline: {
        baseline_id: "e2e-manufacturer-only-v1",
        status: "frozen_manufacturer_only",
        sha256: "b".repeat(64),
        authority: "manufacturer_official_only",
        sources: [],
      },
      catalog_identity: {
        base_device: "STM32F103C8",
        package: "LQFP48",
        pin_count: 48,
        flash_size: "64 KiB",
      },
      device: {
        identity: {
          ambient_temperature_c: { min: -40, max: 85 },
        },
        operating_electrical: {
          vdd_v: { min: 2, max: 3.6 },
          io_supply_v: { min: 2, max: 3.6 },
          vdda_v: { min: 2, max: 3.6 },
        },
        memory_map: {
          main_flash: {
            start: "0x08000000",
            end: "0x0800FFFF",
            size_bytes: 65536,
            page_size_bytes: 1024,
            page_count: 64,
          },
          sram: {
            start: "0x20000000",
            end: "0x20004FFF",
            size_bytes: 20480,
          },
        },
      },
      programming: {
        interfaces: {
          SWD: {
            clock_hz: {
              manufacturer_min: null,
              manufacturer_max: null,
              manufacturer_recommended: null,
              status: "not_specified_by_locked_manufacturer_sources",
            },
            required_signal_pins: [
              { signal: "SWDIO", mcu_pin: "PA13" },
              { signal: "SWCLK", mcu_pin: "PA14" },
            ],
          },
          system_bootloader: {
            status: "known_interface_not_expanded_in_v1",
            boot_source: "system_memory",
            transport_detail: "requires separate documentation",
          },
        },
        electrical: {
          vdd_programming_v: { min: 2, max: 3.6 },
          external_vpp: { required: false },
        },
        flash_geometry: {
          erase_unit: "page",
          erase_unit_bytes: 1024,
          program_unit: "halfword",
          program_unit_bytes: 2,
          program_alignment_bytes: 2,
          mass_erase_supported: true,
          verify_by_readback: true,
        },
        flash_controller: {},
        special_constraints: [],
        program_model: {
          normal_write_flow: ["unlock", "erase", "program", "verify"],
          not_yet_modeled: [],
          operations: {},
        },
      },
      plasma_compatibility: {
        site_electrical_compatibility: "not_evaluated",
        socket_compatibility: "not_evaluated",
        hardware_runtime_ready: false,
        physical_programming_qualified: false,
      },
      ic_support: {
        binding_set_id: "e2e",
        binding_status: "validated",
        profiles: {},
      },
    } : null,
  });

  await page.route("**/api/devices/search**", async route => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get("q") ?? "";
    const limit = Number(url.searchParams.get("limit") ?? "30");
    const offset = Number(url.searchParams.get("offset") ?? "0");
    if (!query) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          query,
          catalog_size: 4641,
          count: 0,
          total_count: 0,
          limit,
          offset,
          results: [],
        }),
      });
      return;
    }
    const all = Array.from({ length: 31 }, (_, index) =>
      makeResult(index === 0 ? "STM32F103C8T6" : `STM32F103TEST${String(index).padStart(2, "0")}`, index === 0),
    );
    const results = all.slice(offset, offset + limit);
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        query,
        catalog_size: 4641,
        count: results.length,
        total_count: all.length,
        limit,
        offset,
        results,
      }),
    });
  });

  await page.goto("/devices");
  const search = page.getByRole("textbox", { name: "Search admitted ICPN" });
  await search.fill("STM32F");

  await expect(page.getByText("顯示 1–30 / 共 31 筆")).toBeVisible();
  await page.getByRole("listitem").first().click();
  await expect(page.getByRole("heading", { name: "STM32F103C8T6" })).toBeVisible();
  const deviceInfo = page.locator('[data-profile-section="device"]');
  await expect(deviceInfo.getByText("STM32F103C8T6", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("STM32F103C8", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("LQFP", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("48", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("64 KiB", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("20 KiB", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("2–3.6 V", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("-40–85 °C", { exact: true })).toBeVisible();
  await expect(deviceInfo.getByText("Memory Map", { exact: true })).toHaveCount(0);
  await expect(deviceInfo.getByText("I/O supply", { exact: true })).toHaveCount(0);
  await expect(deviceInfo.getByText("VDDA", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Known Interface Not Expanded In V1")).toBeVisible();
  expect(pageErrors).toEqual([]);

  await page.getByRole("button", { name: "下一頁 →" }).click();
  await expect(page.getByText("顯示 31–31 / 共 31 筆")).toBeVisible();
  await expect(page.getByText("第 2 / 2 頁")).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText("尚未選擇 ICPN")).toBeVisible();

  await page.getByRole("button", { name: "← 上一頁" }).click();
  await expect(page.getByText("顯示 1–30 / 共 31 筆")).toBeVisible();
  expect(pageErrors).toEqual([]);
});
