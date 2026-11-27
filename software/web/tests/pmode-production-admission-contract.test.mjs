import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");

test("PMode admits Target IC through the Manager Programming Route, not a Browser capability resolver (U10)", () => {
  assert.match(source, /const icpn = targetDevice\?\.icpn \?\? targetDevice\?\.identifier \?\? null;/);
  assert.match(source, /if \(!icpn\) return blocked\("no-target", "NO TARGET", "Select a Target IC\."\);/);
  assert.match(source, /const blocker = managedBatchBlocker\(managedTopology, managedRoutes\.routes, icpn,/);
  assert.doesNotMatch(source, /resolveProgrammingCapabilities|syntheticProgrammingImageAvailable|allowSyntheticMockImage/);
  assert.doesNotMatch(source, /catalog\?\.provider === "mock"/);
});

test("PMode removes disabled Sites from the next Batch membership without changing the Production Set", () => {
  assert.match(source, /enabledSiteIds = new Set\(runtime\.sites\.filter\(site => site\.enabled\)/);
  assert.match(source, /enabledSelection = siteIds\.filter\(siteId => enabledSiteIds\.has\(siteId\)\)/);
  assert.match(source, /setBatchSelection\(current => \{/);
  assert.doesNotMatch(source, /setProductionSet\(current =>[\s\S]{0,400}enabledSiteIds/);
  assert.match(source, /disabled=\{batchRunning \|\| !site\.enabled\}/);
});
