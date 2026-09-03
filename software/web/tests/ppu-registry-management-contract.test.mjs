import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const ppuSite = await readFile(new URL("../app/engineering/ppu-site-configuration.tsx", import.meta.url), "utf8");
const ppuNetwork = await readFile(new URL("../app/engineering/ppu-network-configuration.tsx", import.meta.url), "utf8");
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

test("PPU management names the northbound service Plasma Gateway", () => {
  assert.match(ppuSite, /Plasma Gateway Endpoint/);
  assert.match(ppuSite, /Add a Plasma Gateway to the Manager registry/);
  assert.match(ppuSite, /<th>Plasma Gateway<\/th>/);
  assert.doesNotMatch(ppuSite, /<span>Gateway Endpoint<\/span>|<dt>Gateway Endpoint<\/dt>|<th>Gateway<\/th>/);
});

test("PPU network desired state is rendered inside PPU/Site management", () => {
  assert.match(ppuSite, /import PpuNetworkConfiguration/);
  assert.match(ppuSite, /<PpuNetworkConfiguration/);
  assert.match(ppuSite, /hasActiveExecution=\{selectedHasActiveExecution\}/);
  assert.match(ppuNetwork, /PPU Network Configuration/);
  assert.match(ppuNetwork, /Save Desired Network/);
  assert.match(ppuNetwork, /Running <code>eth0<\/code> was not activated/);
});

test("PPU network UI distinguishes Linux Default Gateway from the Plasma Gateway service", () => {
  assert.match(ppuNetwork, /<span>Default Gateway<\/span>/);
  assert.match(ppuNetwork, /aria-label="PPU static default gateway"/);
  assert.match(ppuNetwork, /Default Gateway is the Linux Layer-3 next-hop router/);
  assert.match(ppuNetwork, /It is not the Plasma Gateway service running on this PPU/);
  assert.doesNotMatch(ppuNetwork, /<span>Gateway<\/span>/);
});

test("PPU network browser client uses alias-scoped Manager BFF and never calls activation directly", () => {
  assert.match(registryApi, /getManagerPpuNetwork/);
  assert.match(registryApi, /saveManagerPpuNetwork/);
  assert.match(registryApi, /\/api\/manager\/registry\/\$\{encodeURIComponent\(alias\)\}\/network/);
  assert.match(registryApi, /Idempotency-Key/);
  assert.doesNotMatch(ppuNetwork, /\/api\/settings\/ppu-network\/activation/);
  assert.doesNotMatch(ppuNetwork, /fetch\(/);
  assert.match(ppuNetwork, /Manager-orchestrated apply/);
});

test("browser registry client exposes add, lifecycle, remove, and desired network settings through same-origin BFF", () => {
  assert.match(registryApi, /\/api\/manager\/registry/);
  assert.match(registryApi, /method: "POST"/);
  assert.match(registryApi, /method: "PATCH"/);
  assert.match(registryApi, /method: "DELETE"/);
  assert.doesNotMatch(registryApi, /127\.0\.0\.1:18180/);
});

test("Manager registry BFF remains loopback-only and mutation requires managed Control Station mode", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /relayManagerRegistryRequest/);
  assert.match(managerBff, /relayManagerPpuAliasRequest/);
  assert.match(managerBff, /requireManagedMode = false/);
  assert.match(managerBff, /relayManagerRequest\(request, `\/api\/registry\$\{suffix\}`, bodyAllowed, true\)/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL/);
});

test("registry BFF routes keep inventory mutations and alias-scoped network relay explicit", () => {
  assert.match(registryRoute, /export async function GET/);
  assert.match(registryRoute, /export async function POST/);
  assert.doesNotMatch(registryRoute, /export async function PATCH|export async function DELETE/);
  assert.match(registryEntryRoute, /resource: "entry" \| "network"/);
  assert.match(registryEntryRoute, /relayManagerPpuAliasRequest\(request, parsed\.alias, "\/api\/settings\/ppu-network"\)/);
  assert.match(registryEntryRoute, /export async function GET/);
  assert.match(registryEntryRoute, /export async function POST/);
  assert.match(registryEntryRoute, /export async function PATCH/);
  assert.match(registryEntryRoute, /export async function DELETE/);
});
