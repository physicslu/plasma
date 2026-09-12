import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");

test("PMode requires an explicit production-admitted Target IC independent of provider kind", () => {
  assert.match(source, /targetValid:\s*Boolean\(targetDevice\)/);
  assert.match(source, /if \(!targetDevice\) \{[\s\S]*?setOperatorWarning\(text\.chooseTarget\)/);
  assert.doesNotMatch(source, /targetValid:\s*syntheticMockImageAvailable\s*\|\|\s*Boolean\(targetDevice\)/);
  assert.doesNotMatch(source, /if \(!targetDevice && !syntheticMockImageAvailable\)/);
});

test("PMode removes disabled Sites from the next Batch membership without changing the Production Set", () => {
  assert.match(source, /enabledSiteIds = new Set\(runtime\.sites\.filter\(site => site\.enabled\)/);
  assert.match(source, /enabledSelection = siteIds\.filter\(siteId => enabledSiteIds\.has\(siteId\)\)/);
  assert.match(source, /setBatchSelection\(current => \{/);
  assert.doesNotMatch(source, /setProductionSet\(current =>[\s\S]{0,400}enabledSiteIds/);
  assert.match(source, /disabled=\{batchRunning \|\| !site\.enabled\}/);
});
