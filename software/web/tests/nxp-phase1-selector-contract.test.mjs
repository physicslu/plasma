import fs from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";

const source = async (p) => fs.readFile(new URL(p, import.meta.url), "utf8");

test("NXP Phase 1 is distinct from software qualified catalog and legacy NXP profile", async () => {
  const api = await source("../app/device-catalog-api.ts");
  const selector = await source("../app/devices/ic-selector.tsx");
  const css = await source("../app/devices/devices.css");

  assert.match(api, /type NXPPhase1Information/);
  assert.match(api, /research_field_evidence_only/);
  assert.match(api, /nxp_phase1_information\?: NXPPhase1Information \| null/);
  assert.match(api, /programming_qualified: false/);
  assert.match(selector, /selected\.nxp_phase1_information\.fields\.ram/);
  assert.match(selector, /selected\.nxp_phase1_information\.fields\.working_vdd/);
  assert.match(selector, /selected\.nxp_phase1_information\.fields\.vdda/);
  assert.match(selector, /selected\.nxp_phase1_information\.fields\.io_supply/);
  assert.match(selector, /data-evidence-state=\{field\.state\}/);
  assert.match(selector, /field\.value === null/);
  assert.match(selector, /NXP 原廠來源/);
  assert.match(selector, /rel="noopener noreferrer"/);
  assert.match(selector, /不代表可燒錄/);
  assert.match(css, /\.icSelectorPhase1State\[data-evidence-state="PARTIAL"\]/);
  assert.match(selector, /data-profile-section="programming"/);
  assert.match(selector, /data-profile-section="compatibility"/);
});
