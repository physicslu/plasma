import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Programming is a Production workspace rather than a global utility", async () => {
  const globalNav = await source("../app/global-nav.tsx");
  const productionNav = await source("../app/fleet/production-workspace-nav.tsx");

  assert.doesNotMatch(globalNav, /href="\/fleet\/programming"/);
  assert.match(globalNav, /href="\/devices"/);
  assert.match(productionNav, /aria-label="Production workspaces"/);
  assert.match(productionNav, /href="\/fleet"/);
  assert.match(productionNav, /href="\/fleet\/programming"/);
  assert.match(productionNav, /Single PPU Programming/);
});

test("both Production pages render the shared workspace navigation", async () => {
  const factoryPage = await source("../app/fleet/page.tsx");
  const programmingPage = await source("../app/fleet/programming/page.tsx");

  assert.match(factoryPage, /ProductionWorkspaceNav/);
  assert.match(programmingPage, /ProductionWorkspaceNav/);
});
