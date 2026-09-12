import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");

test("PMode derives Target IC and Synthetic Image admission from shared programming capabilities", () => {
  assert.match(source, /resolveProgrammingCapabilities\(catalog\)/);
  assert.match(source, /targetValid:\s*!programmingCapabilities\.target_device_required \|\| Boolean\(targetDevice\)/);
  assert.match(source, /if \(!targetDevice && programmingCapabilities\.target_device_required\)/);
  assert.match(source, /syntheticProgrammingImageAvailable = programmingCapabilities\.synthetic_programming_image/);
  assert.match(source, /allowSyntheticMockImage:\s*syntheticProgrammingImageAvailable/);
  assert.doesNotMatch(source, /catalog\?\.provider === "mock"/);
});

test("PMode removes disabled Sites from the next Batch membership without changing the Production Set", () => {
  assert.match(source, /enabledSiteIds = new Set\(runtime\.sites\.filter\(site => site\.enabled\)/);
  assert.match(source, /enabledSelection = siteIds\.filter\(siteId => enabledSiteIds\.has\(siteId\)\)/);
  assert.match(source, /setBatchSelection\(current => \{/);
  assert.doesNotMatch(source, /setProductionSet\(current =>[\s\S]{0,400}enabledSiteIds/);
  assert.match(source, /disabled=\{batchRunning \|\| !site\.enabled\}/);
});
