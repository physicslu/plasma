import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps PPU and Site as the canonical Web vocabulary after legacy console retirement", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  const engineering = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
  const production = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");

  assert.match(api, /export type PPUSnapshot/);
  assert.match(api, /export type SiteSnapshot/);
  assert.match(api, /export async function getPPUStatus/);
  assert.match(engineering, /Select PPU:/);
  assert.match(engineering, /LIVE SITE STATUS/);
  assert.match(engineering, /siteLabel\(site\.id\)/);
  assert.match(production, /PRODUCTION SITE SELECTION/);
  assert.match(production, /LIVE SITE STATUS/);
  assert.match(layout, /title: "Plasma Control Station"/);

  assert.doesNotMatch(engineering, />CHANNEL MATRIX</);
  assert.doesNotMatch(engineering, />LIVE CHANNEL STATUS</);
  assert.doesNotMatch(production, />CHANNEL MATRIX</);
  assert.doesNotMatch(production, />LIVE CHANNEL STATUS</);
  assert.doesNotMatch(layout, /title: "Plasma PPU Console"/);
});
