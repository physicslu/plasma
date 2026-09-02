import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const ppuSite = await readFile(new URL("../app/engineering/ppu-site-configuration.tsx", import.meta.url), "utf8");
const registryApi = await readFile(new URL("../app/engineering/ppu-registry-api.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const registryRoute = await readFile(new URL("../app/api/manager/registry/route.ts", import.meta.url), "utf8");
const registryEntryRoute = await readFile(new URL("../app/api/manager/registry/[...path]/route.ts", import.meta.url), "utf8");

test("EMode keeps its existing navigation and owns PPU management inside the ppu-sites canvas", () => {
  assert.match(engineering, /\["ppu-sites", "engineering\.ppuSites", "▤"\]/);
  assert.match(engineering, /<aside className="engineeringSidebar">/);
  assert.match(engineering, /active === "ppu-sites"/);
  assert.match(engineering, /<PpuSiteConfiguration \/>/);
});

test("PPU management uses Manager-owned registry APIs instead of browser-local inventory", () => {
  assert.match(ppuSite, /getManagerRegistry/);
  assert.match(ppuSite, /addManagerPpu/);
  assert.match(ppuSite, /setManagerPpuLifecycle/);
  assert.match(ppuSite, /removeManagerPpu/);
  assert.match(ppuSite, /Validate &amp; Enable/);
  assert.match(ppuSite, /Remove PPU/);
  assert.doesNotMatch(ppuSite, /const initialPpus/);
  assert.doesNotMatch(ppuSite, /setPpus\(/);
});

test("PPU identity and Site topology remain Manager-observed rather than manually fabricated", () => {
  assert.match(ppuSite, /fleetForEntry/);
  assert.match(ppuSite, /selectedFleet\?\.topology\.site_count/);
  assert.match(ppuSite, /SITE\{site\.site_id\}/);
  assert.match(ppuSite, /PPU-reported topology/);
  assert.match(ppuSite, /Site enabled state shown here is PPU-reported and read-only/);
  assert.doesNotMatch(ppuSite, /Enable All|Disable All/);
});

test("browser registry client exposes add, lifecycle and remove through same-origin BFF", () => {
  assert.match(registryApi, /\/api\/manager\/registry/);
  assert.match(registryApi, /method: "POST"/);
  assert.match(registryApi, /method: "PATCH"/);
  assert.match(registryApi, /method: "DELETE"/);
  assert.doesNotMatch(registryApi, /127\.0\.0\.1:18180/);
});

test("Manager registry BFF remains loopback-only and mutation requires managed Control Station mode", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /relayManagerRegistryRequest/);
  assert.match(managerBff, /requireManagedMode = false/);
  assert.match(managerBff, /relayManagerRequest\(request, `\/api\/registry\$\{suffix\}`, bodyAllowed, true\)/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL/);
});

test("registry BFF routes expose only the expected Manager inventory methods", () => {
  assert.match(registryRoute, /export async function GET/);
  assert.match(registryRoute, /export async function POST/);
  assert.doesNotMatch(registryRoute, /export async function PATCH|export async function DELETE/);
  assert.match(registryEntryRoute, /export async function PATCH/);
  assert.match(registryEntryRoute, /export async function DELETE/);
  assert.doesNotMatch(registryEntryRoute, /export async function GET|export async function POST/);
});
