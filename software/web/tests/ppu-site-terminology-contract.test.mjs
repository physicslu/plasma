import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps PPU and Site as the canonical Web vocabulary", async () => {
  const page = await readFile(new URL("../app/site-matrix-home.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");

  assert.match(api, /export type PPUSnapshot/);
  assert.match(api, /export type SiteSnapshot/);
  assert.match(api, /export async function getPPUStatus/);
  assert.match(page, />SITE MATRIX</);
  assert.match(page, />DISPLAY SITES</);
  assert.match(page, />LIVE SITE STATUS</);
  assert.match(page, /aria-label="PPU identity"/);
  assert.match(page, /Facility <b>\{ppu\.facility_id\}/);
  assert.match(page, /PPU <b>\{ppu\.ppu_id\}/);
  assert.match(page, /<span>SITE \{site\.id\}<\/span>/);
  assert.match(layout, /title: "Plasma PPU Console"/);

  assert.doesNotMatch(page, />CHANNEL MATRIX</);
  assert.doesNotMatch(page, />DISPLAY CHANNELS</);
  assert.doesNotMatch(page, />LIVE CHANNEL STATUS</);
  assert.doesNotMatch(page, /aria-label="Programmer identity"/);
  assert.doesNotMatch(page, />CH\{site\.id\}</);
});
