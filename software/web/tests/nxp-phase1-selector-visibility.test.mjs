import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function read(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("IC Selector lookup includes Phase1 IDENTIFIED, picker remains production only", async () => {
  const selector = await read("../app/devices/ic-selector.tsx");
  const api = await read("../app/device-catalog-api.ts");
  assert.match(selector, /usage === "lookup" \? "phase1" : "production"/);
  assert.match(selector, /visibility: selectorVisibility/);
  assert.match(selector, /phase1_identified/);
  assert.match(selector, /Phase 1 · 已確認身分（尚不可燒錄）/);
  assert.match(selector, /Phase 2 尚未取得軟體燒錄資格/);
  assert.match(api, /visibility\?: "production" \| "phase1"/);
  assert.match(api, /params\.set\("visibility", options\.visibility\)/);
});

test("IC Selector does not enable Phase1 records as executable jobs", async () => {
  const selector = await read("../app/devices/ic-selector.tsx");
  const picker = await read("../app/devices/ic-picker-field.tsx");
  assert.match(selector, /usage === "lookup" \? "phase1" : "production"/);
  assert.doesNotMatch(picker, /visibility:\s*"phase1"/);
  const api = await read("../app/device-catalog-api.ts");
  assert.match(api, /if \(options\.visibility\)/);
});
