import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const read = path => fs.readFile(new URL(path, import.meta.url), "utf8");

test("upstream CFG/Driver/DEVID and production binding are independent UI fields", async () => {
  const selector = await read("../app/devices/ic-selector.tsx");
  const api = await read("../app/device-catalog-api.ts");
  for (const snippet of [
    "Upstream OpenOCD CFG（來源證據）",
    "Upstream Flash Driver（來源證據）",
    "Upstream Device ID／DEVID",
    "PLASMA Production CFG Binding",
    "selected.upstream_openocd_evidence.target_cfg.path",
    "selected.upstream_openocd_evidence.flash_driver.path",
    "selected.upstream_openocd_evidence.device_id.value",
    "selected.backend.mapping_status",
    "source_only_non_executable",
  ]) {
    assert.ok((selector + api).includes(snippet), `missing split evidence: ${snippet}`);
  }
  assert.match(selector, /PLASMA CFG · 未綁定/);
  assert.match(selector, /未獨立核對（不代表不存在）/);
  assert.match(selector, /不代表已安裝、已綁定、可執行燒錄或實機通過/);
  assert.match(api, /production_binding_authorized: false/);
  assert.match(api, /executable: false/);
  assert.match(api, /physical_programming_qualified: false/);
});

test("Microchip detailed information uses dynamic exact state and family-specific documents", async () => {
  const selector = await read("../app/devices/ic-selector.tsx");
  const api = await read("../app/device-catalog-api.ts");
  assert.match(selector, /selected\.microchip_ic_information\.source\.pdf_revision/);
  assert.match(selector, /selected\.programming_qualification\?\.state/);
  assert.match(selector, /selected\.catalog_level/);
  assert.match(selector, /selected\.microchip_ic_information\.programming_state/);
  assert.doesNotMatch(selector, /Catalog Level 0 Evidence/);
  assert.doesNotMatch(selector, /Catalog Level 0 DISCOVERED/);
  assert.doesNotMatch(selector, /DS60001513G p\.14 \/ p\.16/);
  assert.match(api, /pdf_revision\?: "DS60001513G"/);
  assert.match(api, /"manufacturer_exact_material_identity_route_candidate"/);
  assert.match(api, /upstream_openocd_evidence\?: UpstreamOpenOCDEvidence/);
});

test("upstream evidence projection cannot mutate qualification, mapping or runtime", async () => {
  const code = await read("../../python/plasma_web/microchip_upstream_openocd_evidence.py");
  const gateway = await read("../../python/plasma_web/gateway.py");
  assert.match(code, /PIC32MX_BASE_DEVID\.get\(row\.base_device\)/);
  assert.match(code, /expected_devid=\{devid\}/);
  assert.match(code, /source_commit=\{PIC32_PINNED_COMMIT\}/);
  assert.match(code, /"production_binding_authorized": False/);
  assert.match(code, /"executable": False/);
  assert.match(code, /"physical_programming_qualified": False/);
  assert.match(gateway, /item\["upstream_openocd_evidence"\] = microchip_upstream_openocd_evidence\(record\)/);
  assert.doesNotMatch(code, /subprocess|os\.system|flash_write|job_selectable\s*=(?!=)|row\.mapping_status\s*=(?!=)/);
});
