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

  assert.match(programmingPage, /redirect\("\/fleet"\)/);
  // U10: the standalone Render SPA that mirrored this redirect is retired.
  await assert.rejects(fs.access(new URL("../render", import.meta.url)));
});

test("Factory Console v2 owns the Production viewport without retired selector layout CSS", async () => {
  const css = await source("../app/fleet/factory-console-v2.css");

  assert.match(css, /\.factoryConsoleV2\s*\{[\s\S]*min-height:\s*100vh/);
  assert.match(css, /\.factoryConsoleV2\s*\{[\s\S]*padding:\s*10px 12px 22px/);
  assert.doesNotMatch(css, /productionPrototypePage|fpsSelector/);
});
