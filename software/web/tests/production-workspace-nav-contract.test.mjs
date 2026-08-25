import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Production Mode exposes one Factory Console surface without a local workspace navigation bar", async () => {
  const globalNav = await source("../app/global-nav.tsx");
  const fleetPage = await source("../app/fleet/page.tsx");

  assert.doesNotMatch(globalNav, /href="\/fleet\/programming"/);
  assert.doesNotMatch(fleetPage, /ProductionWorkspaceNav/);
  assert.match(fleetPage, /FactoryConsoleV2/);
});

test("retired Production Single PPU route redirects to the Factory Console", async () => {
  const programmingPage = await source("../app/fleet/programming/page.tsx");
  const renderEntry = await source("../render/main.tsx");
  const renderNavigation = await source("../render/next-navigation.ts");

  assert.match(programmingPage, /redirect\("\/fleet"\)/);
  assert.doesNotMatch(renderEntry, /FleetProgrammingPage/);
  assert.match(renderEntry, /RetiredFleetProgrammingRoute/);
  assert.match(renderEntry, /replaceRoute\("\/fleet"\)/);
  assert.match(renderNavigation, /export function replaceRoute/);
  assert.match(renderNavigation, /window\.history\.replaceState/);
});

test("Production reclaims the viewport budget previously consumed by the removed workspace navigation", async () => {
  const css = await source("../app/fleet/fps-selector-layout.css");

  assert.match(css, /height:\s*min\(960px, calc\(100dvh - 150px\)\)/);
  assert.match(css, /max-height:\s*min\(960px, calc\(100dvh - 150px\)\)/);
  assert.doesNotMatch(css, /100dvh - 200px/);
});
