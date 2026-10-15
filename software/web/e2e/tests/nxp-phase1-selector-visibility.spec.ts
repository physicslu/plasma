import { expect, test } from "@playwright/test";

test("NXP Phase 1 IDENTIFIED exact ICPN is searchable in IC Selector, not labeled programmable", async ({ page }) => {
  const observedVisibilities: string[] = [];
  const icpn = "LPC11U68JBD48E";
  await page.route("**/api/devices/search**", async route => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q") ?? "";
    observedVisibilities.push(url.searchParams.get("visibility") ?? "production");
    const data = q === icpn ? [{
      vendor: "NXP",
      family: "LPC11U6X",
      subfamily: "LPC11U68JBD48",
      plasma_series: "LPC11U6X",
      identifier: icpn,
      identifier_kind: "manufacturer_part_number",
      icpn,
      package: "LQFP48",
      pin_count: null,
      flash_size: "256 kB",
      temperature_grade: null,
      option_suffix: null,
      base_device: "LPC11U68JBD48",
      cpu_architectures: [],
      backend: {
        type: "openocd",
        distribution: "",
        target_config: "",
        mapping_status: "no_mapping",
        mapping_method: null,
      },
      catalog_verification: {
        status: "verified_phase1_identified",
        source_type: "official_nxp_exact_material_12nc",
        source_authority: "https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab",
        source_reference: "NXP 12NC=935303821551",
      },
      physical_validation: {
        engineering_status: "no_evidence",
        ppu_status: "no_evidence",
        socket_status: "no_evidence",
      },
      catalog: {
        scope: "phase1_identified",
        version: "NXP-Phase1-source-locked-v1",
        revision_sha256: null,
      },
      catalog_origin: "nxp_phase1_identified_official_material",
      phase1: { identity_state: "IDENTIFIED", information_complete: false },
      backend_candidate: null,
      backend_source_reference: null,
      backend_providers: [],
      manufacturer_device_basic_profile: null,
      nxp_manufacturer_device_profile: null,
      selected_profile: null,
      openocd_software_qualification: null,
    }] : [];
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true, visibility: "phase1", query: q,
        catalog_size: 4926, count: data.length, total_count: data.length,
        limit: Number(url.searchParams.get("limit") ?? 30),
        offset: Number(url.searchParams.get("offset") ?? 0),
        results: data,
      }),
    });
  });

  await page.goto("/devices");
  const search = page.getByRole("textbox", { name: "Search Phase 1 identified ICPN" });
  await search.fill(icpn);
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText("Phase 1 · 已確認身分（尚不可燒錄）")).toBeVisible();
  await page.getByRole("listitem").click();
  await expect(page.locator("aside.icSelectorDetail").getByRole("heading", { name: icpn })).toBeVisible();
  await expect(page.getByText(/Phase 2 尚未取得軟體燒錄資格/)).toBeVisible();
  expect(observedVisibilities.length).toBeGreaterThan(0);
  expect(observedVisibilities.every(x => x === "phase1")).toBeTruthy();
});
