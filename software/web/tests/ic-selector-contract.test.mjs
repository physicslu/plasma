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

test("IC Selector presents admitted exact ICPN evidence without inventing physical verification", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const api = await source("../app/device-catalog-api.ts");

  assert.match(api, /\/api\/devices\/search/);
  assert.match(api, /catalog_verification/);
  assert.match(api, /revision_sha256/);
  assert.match(selector, /ICPN CATALOG · PRODUCTION ADMITTED/);
  assert.match(selector, /Exact ICPN/);
  assert.match(selector, /OCD Mapped/);
  assert.match(selector, /Catalog Revision/);
  assert.match(selector, /Authority/);
  assert.match(selector, /PPU ·/);
  assert.match(selector, /Socket ·/);
  assert.match(selector, /無實體證據/);
  assert.match(selector, /仍不等於 PPU 或 Socket 實體驗證/);
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
