import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("IC Selector is a reusable global capability, not a product mode", async () => {
  const productMode = await source("../app/product-mode.ts");
  const globalNav = await source("../app/global-nav.tsx");
  const page = await source("../app/devices/page.tsx");
  const selector = await source("../app/devices/ic-selector.tsx");

  assert.doesNotMatch(productMode, /devices/);
  assert.match(globalNav, /className="globalUtilityNav"/);
  assert.match(globalNav, /href="\/devices"/);
  assert.match(page, /<ICSelector usage="lookup"/);
  assert.match(selector, /ICSelectorUsage\s*=\s*"lookup"\s*\|\s*"picker"/);
  assert.match(selector, /onSelect\?:\s*\(device:\s*DeviceSearchResult\)\s*=>\s*void/);
});

test("global IC lookup remains outside execution mode-switch locking", async () => {
  const globalNav = await source("../app/global-nav.tsx");
  const utilityNav = globalNav.match(/<nav className="globalUtilityNav"[\s\S]*?<\/nav>/)?.[0];

  assert.ok(utilityNav, "global utility navigation must exist");
  assert.match(utilityNav, /href="\/devices"/);
  assert.doesNotMatch(utilityNav, /aria-disabled/);
  assert.doesNotMatch(utilityNav, /blockLockedNavigation/);
});

test("IC Selector presents catalog evidence without inventing physical verification", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /\/api\/devices\/search/);
  assert.match(selector, /OCD Candidate/);
  assert.match(selector, /PPU ·/);
  assert.match(selector, /Socket ·/);
  assert.match(selector, /No evidence/);
  assert.match(selector, /OpenOCD mapping 不等於 PPU 或 Socket 驗證/);
  assert.doesNotMatch(selector, /\?\.toLocaleString\(\) \?\? "7,657"/);
});
