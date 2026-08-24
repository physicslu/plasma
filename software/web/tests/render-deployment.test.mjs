import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Render build reuses canonical React pages and resolves API requests at the browser origin", async () => {
  const entry = await readFile(new URL("../render/main.tsx", import.meta.url), "utf8");
  const config = await readFile(new URL("../render/vite.config.ts", import.meta.url), "utf8");

  assert.match(entry, /from "\.\.\/app\/demo\/page"/);
  assert.match(entry, /from "\.\.\/app\/devices\/page"/);
  assert.match(entry, /from "\.\.\/app\/engineering\/page"/);
  assert.match(entry, /from "\.\.\/app\/fleet\/page"/);
  assert.match(entry, /from "\.\.\/app\/fleet\/programming\/page"/);
  assert.match(entry, /from "\.\.\/app\/page"/);
  assert.match(entry, /<WorkspaceSessionProvider>/);
  assert.match(config, /"process\.env\.NEXT_PUBLIC_PLASMA_API_URL": "window\.location\.origin"/);
  assert.match(config, /"next\/link"/);
  assert.match(config, /"next\/navigation"/);
  assert.match(config, /dist-render/);
});

test("Render client router maps canonical standalone pages instead of falling back to the portal", async () => {
  const entry = await readFile(new URL("../render/main.tsx", import.meta.url), "utf8");

  assert.match(entry, /pathname === "\/devices"[\s\S]*<DevicesPage \/>/);
  assert.match(entry, /pathname === "\/fleet\/programming"[\s\S]*<FleetProgrammingPage \/>/);

  const programmingIndex = entry.indexOf('pathname === "/fleet/programming"');
  const fleetIndex = entry.indexOf('pathname === "/fleet" || pathname.startsWith("/fleet/")');
  assert.ok(programmingIndex >= 0 && fleetIndex >= 0 && programmingIndex < fleetIndex,
    "the exact Programming route must be resolved before the /fleet prefix route");
});

test("Render navigation preserves a single existing workspace session between product modes", async () => {
  const navigation = await readFile(new URL("../render/next-navigation.ts", import.meta.url), "utf8");
  const link = await readFile(new URL("../render/next-link.tsx", import.meta.url), "utf8");

  assert.match(navigation, /window\.history\.pushState/);
  assert.match(navigation, /useSyncExternalStore/);
  assert.match(link, /event\.preventDefault\(\)/);
  assert.match(link, /navigate\(/);
  assert.doesNotMatch(link, /window\.location\.assign/);
});
