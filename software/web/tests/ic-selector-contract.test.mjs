import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("IC Selector is a reusable lookup capability entered from the portal, not a product mode", async () => {
  const productMode = await source("../app/product-mode.ts");
  const globalNav = await source("../app/global-nav.tsx");
  const demo = await source("../app/demo/page.tsx");
  const page = await source("../app/devices/page.tsx");
  const selector = await source("../app/devices/ic-selector.tsx");

  assert.doesNotMatch(productMode, /devices/);
  assert.doesNotMatch(globalNav, /className="globalUtilityNav"/);
  assert.doesNotMatch(globalNav, /href="\/devices"/);
  assert.match(demo, /<span>03<\/span>/);
  assert.match(demo, /href="\/devices"/);
  assert.match(demo, /<h2>IC Selector<\/h2>/);
  assert.match(page, /<ICSelector usage="lookup"/);
  assert.match(selector, /ICSelectorUsage\s*=\s*"lookup"\s*\|\s*"picker"/);
  assert.match(selector, /onSelect\?:\s*\(device:\s*DeviceSearchResult\)\s*=>\s*void/);
});

test("IC lookup remains outside the canonical Product Mode navigation", async () => {
  const globalNav = await source("../app/global-nav.tsx");
  const demo = await source("../app/demo/page.tsx");

  const productNav = globalNav.match(/<nav className="globalProductNav"[\s\S]*?<\/nav>/)?.[0];
  assert.ok(productNav, "canonical Product Mode navigation must exist");
  assert.doesNotMatch(productNav, /\/devices/);
  assert.match(demo, /className=\{`demoCard utility \$\{devicesDisabled \? "disabled" : ""\}`\}[\s\S]*?href="\/devices"/);
  assert.match(demo, /principalHasPermission\(principal, "catalog\.read"\)/);
  assert.doesNotMatch(demo, /blockLockedNavigation/);
});

test("IC Selector separates hardware-test status from OpenOCD and manufacturer-part evidence", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const styles = await source("../app/devices/devices.css");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /\/api\/devices\/search/);
  assert.match(api, /catalog_verification/);
  assert.match(api, /physical_validation/);
  assert.match(api, /revision_sha256/);
  assert.match(selector, /ICPN CATALOG · PRODUCTION ADMITTED/);
  assert.match(selector, /Exact ICPN/);
  assert.match(selector, /Catalog Revision/);
  assert.match(selector, /Authority/);
  assert.match(selector, /icSelectorStatusStack/);
  assert.match(selector, /icSelectorStatusPhysical[\s\S]*physicalValidationLabel\("PPU"[\s\S]*physicalValidationLabel\("Socket"/);
  assert.match(selector, /icSelectorStatusEvidence[\s\S]*openOcdConfigLabel[\s\S]*manufacturerPartLabel/);
  assert.match(selector, /OpenOCD 設定 · 已存在/);
  assert.match(selector, /原廠料號 · 已確認/);
  assert.match(selector, /未實機測試/);
  assert.match(selector, /實機測試通過/);
  assert.match(selector, /device\.physical_validation\.ppu_status/);
  assert.match(selector, /device\.physical_validation\.socket_status/);
  assert.match(selector, /原廠料號已確認且 OpenOCD 設定已存在/);
  assert.doesNotMatch(selector, /無實體證據/);
  assert.match(styles, /\.icSelectorStatusStack\s*\{[^}]*display:\s*grid/);
  assert.match(styles, /\.icSelectorStatusStack\s*\{[^}]*gap:\s*5px/);
  assert.match(selector, /research candidate 不會出現在這裡/);
  assert.doesNotMatch(selector, /OCD Candidate/);
  assert.doesNotMatch(selector, /LPC845/);
  assert.doesNotMatch(selector, /nRF52840/);
});

test("shared PMode and EMode picker is constrained to admitted exact ICPNs", async () => {
  const picker = await source("../app/devices/ic-picker-field.tsx");

  assert.match(picker, /Search admitted ICPN/);
  assert.match(picker, /Exact ICPN ·/);
  assert.match(picker, /OCD Mapped/);
  assert.doesNotMatch(picker, /IC identifier/);
});

test("IC Selector reports total filtered matches and uses a balanced desktop detail layout", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const styles = await source("../app/devices/devices.css");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /total_count:\s*number/);
  assert.match(selector, /setTotalCount\(payload\.total_count\)/);
  assert.match(selector, /顯示/);
  assert.match(selector, /共/);
  assert.match(styles, /\.icSelector\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  assert.match(styles, /\.icSelectorResult\s*\{[\s\S]*?grid-template-columns:\s*minmax\(150px, \.85fr\) minmax\(0, 1\.15fr\)/);
  assert.match(styles, /\.icSelectorStatusStack\s*\{[\s\S]*?grid-column:\s*1 \/ -1/);
  assert.match(styles, /@media \(max-width: 1050px\)[\s\S]*?\.icSelector\s*\{\s*grid-template-columns:\s*1fr/);
});

test("IC Selector paginates server-side and resets selection across result pages", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const styles = await source("../app/devices/devices.css");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /offset:\s*number/);
  assert.match(api, /offset\?:\s*number/);
  assert.match(api, /offset:\s*String\(offset\)/);
  assert.match(selector, /SEARCH_PAGE_SIZE\s*=\s*30/);
  assert.match(selector, /offset:\s*pageOffset/);
  assert.match(selector, /setPageOffset\(0\)/);
  assert.match(selector, /setSelected\(null\)/);
  assert.match(selector, /上一頁/);
  assert.match(selector, /下一頁/);
  assert.match(selector, /Math\.ceil\(totalCount \/ SEARCH_PAGE_SIZE\)/);
  assert.match(styles, /\.icSelectorPagination\s*\{/);
});

test("heterogeneous manufacturer interfaces cannot crash selected-profile rendering", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /clock_hz\?:/);
  assert.match(api, /status\?:\s*string/);
  assert.match(selector, /iface\.clock_hz \? formatClock\(iface\.clock_hz, zh\) : humanizeStatus\(iface\.status \?\? null\)/);
  assert.match(selector, /No debug clock defined for this interface/);
});

test("IC Information uses the independent Manufacturer Device Basic Profile", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /ManufacturerDeviceBasicProfile/);
  assert.match(api, /manufacturer_device_basic_profile\?:\s*ManufacturerDeviceBasicProfile\s*\|\s*null/);
  assert.match(api, /source_surface:\s*"st_product_selector"\s*\|\s*"st_estore"/);
  assert.match(api, /evidence_strength:\s*"official_product_selector_observation"\s*\|\s*"official_estore_observation"/);
  assert.match(selector, /selected\.manufacturer_device_basic_profile/);
  assert.match(selector, /<dt>ICPN<\/dt>/);
  assert.match(selector, /<dt>Base Device<\/dt>/);
  assert.match(selector, /<dt>Package<\/dt>/);
  assert.match(selector, /<dt>Pin Count<\/dt>/);
  assert.match(selector, /<dt>Flash<\/dt>/);
  assert.match(selector, /<dt>RAM<\/dt>/);
  assert.match(selector, /工作 VDD/);
  assert.match(api, /io_supply_v:\s*\{ min: number; max: number \}\s*\|\s*null/);
  assert.match(api, /vdda_v:\s*\{ min: number; max: number \}\s*\|\s*null/);
  assert.match(selector, /<dt>I\/O Supply<\/dt>/);
  assert.match(selector, /<dt>VDDA<\/dt>/);
  // NXP exact manufacturer evidence is distinct from ST Basic Profiles.
  assert.match(api, /NXPManufacturerDeviceProfile/);
  assert.match(api, /nxp_manufacturer_device_profile\?:\s*NXPManufacturerDeviceProfile\s*\|\s*null/);
  assert.match(api, /manufacturer_device_full_profile_complete:\s*false/);
  assert.match(api, /programming_profile_authority:\s*false/);
  assert.match(selector, /selected\.nxp_manufacturer_device_profile/);
  assert.match(selector, /Not independently sourced/);
  assert.match(selector, /工作溫度/);
  assert.doesNotMatch(selector, /<dt>Main Flash Map<\/dt>/);
  assert.doesNotMatch(selector, /<dt>Memory Map<\/dt>/);
});

test("selected IC profile presents device, programming, and Plasma compatibility as separate layers", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const styles = await source("../app/devices/devices.css");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /SelectedICProfile/);
  assert.match(api, /ManufacturerDeviceBasicProfile/);
  assert.match(api, /selected_profile\?:\s*SelectedICProfile\s*\|\s*null/);
  assert.match(api, /manufacturer_device_basic_profile\?:\s*ManufacturerDeviceBasicProfile\s*\|\s*null/);
  assert.match(selector, /data-profile-section="device"/);
  assert.match(selector, /data-profile-section="programming"/);
  assert.match(selector, /data-profile-section="compatibility"/);
  assert.match(selector, /IC Information/);
  assert.match(selector, /Programming VDD/);
  assert.match(selector, /PLASMA Compatibility/);
  assert.match(selector, /原廠文件未明確指定/);
  assert.match(selector, /manufacturer_baseline\.sha256/);
  assert.match(selector, /hardware_runtime_ready/);
  assert.match(selector, /physical_programming_qualified/);
  assert.match(styles, /\.icSelectorProfileSection\s*\{/);
  assert.match(styles, /\.icSelectorEvidenceDetails\s*\{/);
});
