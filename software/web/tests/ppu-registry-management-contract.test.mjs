import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const ppuSite = await readFile(new URL("../app/engineering/ppu-site-configuration.tsx", import.meta.url), "utf8");
const ppuSiteDesired = await readFile(new URL("../app/engineering/ppu-site-desired-configuration.tsx", import.meta.url), "utf8");
const ppuSiteDesiredCore = await readFile(new URL("../app/engineering/ppu-site-desired-configuration-core.tsx", import.meta.url), "utf8");
const ppuRuntimeActivation = await readFile(new URL("../app/engineering/ppu-runtime-activation.tsx", import.meta.url), "utf8");
const ppuUiState = await readFile(new URL("../app/engineering/ppu-ui-state.ts", import.meta.url), "utf8");
const ppuNetwork = await readFile(new URL("../app/engineering/ppu-network-configuration.tsx", import.meta.url), "utf8");
const registryApi = await readFile(new URL("../app/engineering/ppu-registry-api.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedSelectionRoute = await readFile(new URL("../app/api/manager/ppu/route.ts", import.meta.url), "utf8");
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

test("P0 PPU UI keeps Lifecycle, Connectivity, and Health as orthogonal state dimensions", () => {
  assert.match(ppuSite, /<th>Lifecycle<\/th>/);
  assert.match(ppuSite, /<th>Connectivity<\/th>/);
  assert.match(ppuSite, /<th>Health<\/th>/);
  assert.match(ppuSite, /aria-label="PPU orthogonal state dimensions"/);
  assert.match(ppuSite, /lifecycleState\(entry\)/);
  assert.match(ppuSite, /connectivityState\(fleetView\)/);
  assert.match(ppuSite, /healthState\(fleetView\)/);
  assert.doesNotMatch(ppuSite, /<th>Status<\/th>/);
  assert.match(ppuUiState, /entry\.lifecycle === "commissioned"/);
  assert.match(ppuUiState, /fleetView\.transport_state === "unreachable"/);
  assert.match(ppuUiState, /fleetView\.identity_conflict/);
  assert.match(ppuUiState, /fleetView\.degraded/);
});

test("P0 admission UI exposes every Validate prerequisite and explains a blocked action", () => {
  for (const prerequisite of [
    "Observation current",
    "Transport reachable",
    "Execution ready",
    "No identity conflict",
    "Not degraded",
  ]) {
    assert.match(ppuUiState, new RegExp(prerequisite));
  }
  assert.match(ppuSite, /aria-label="Validate prerequisites"/);
  assert.match(ppuSite, /Failing prerequisites:/);
  assert.match(ppuSite, /selectedPrerequisites\.map/);
  assert.match(ppuSite, /disabled=\{!registryMutable \|\| !selectedCanValidate \|\| busyAction !== null\}/);
});

test("validated PPUs can be selected for Managed operations without restarting Console", () => {
  assert.match(registryApi, /selectManagerPpuForManagedOperations/);
  assert.match(registryApi, /"\/api\/manager\/ppu"/);
  assert.match(registryApi, /JSON\.stringify\(\{ ppu_alias: alias \}\)/);
  assert.match(ppuSite, /selectForManagedOperations/);
  assert.match(ppuSite, /Use for Managed Operations/);
  assert.match(ppuSite, /selectedEntry\.lifecycle !== "commissioned"/);
  assert.match(managedSelectionRoute, /managerPpuAliasIsCommissioned\(alias\)/);
  assert.match(managedSelectionRoute, /managerPpuSelectionCookie\(alias\)/);
  assert.match(managerBff, /resolveManagerPpuAlias\(request\)/);
});

test("PPU topology remains observed while Site desired configuration is PPU-owned and writable", () => {
  assert.match(ppuSite, /fleetForEntry/);
  assert.match(ppuSite, /fleetView\?\.topology\.site_count/);
  assert.match(ppuSite, /import PpuSiteDesiredConfiguration/);
  assert.match(ppuSite, /<PpuSiteDesiredConfiguration/);
  assert.match(ppuSiteDesired, /PpuSiteDesiredConfigurationCore/);
  assert.match(ppuSiteDesired, /PpuRuntimeActivation/);
  assert.match(ppuSiteDesiredCore, /getManagerPpuSites/);
  assert.match(ppuSiteDesiredCore, /saveManagerPpuSite/);
  assert.match(ppuSiteDesiredCore, /Desired Enabled/);
  assert.match(ppuSiteDesiredCore, /Desired Interface/);
  assert.match(ppuSiteDesiredCore, /Desired Target/);
  assert.match(ppuSiteDesiredCore, /<th>Runtime<\/th>/);
  assert.match(ppuSiteDesiredCore, /<th>Reconciliation<\/th>/);
  assert.match(ppuSiteDesiredCore, /Stop or cancel active Jobs before changing Site desired configuration/);
  assert.match(ppuSiteDesiredCore, /canonical PPU configuration/);
  assert.doesNotMatch(ppuSite, /Enable All|Disable All/);
});

test("P0 Site UI separates browser Draft, persisted Desired, and observed Runtime without hard-coding topology", () => {
  assert.match(ppuSiteDesiredCore, />Draft</);
  assert.match(ppuSiteDesiredCore, />Desired</);
  assert.match(ppuSiteDesiredCore, />Runtime</);
  assert.match(ppuSiteDesiredCore, /Unsaved Draft/);
  assert.match(ppuSiteDesiredCore, /Saving updates Desired configuration only; Runtime remains separately reconciled/);
  assert.match(ppuSiteDesiredCore, /Topology is discovered from the PPU/);
  assert.doesNotMatch(ppuSiteDesiredCore, /Array\(8\)|SITE8|site_count\s*===\s*8/);
  assert.doesNotMatch(ppuSiteDesiredCore, /Programming Channel|Channel Configuration|CH[1-8]/);
});

test("P3 exposes controlled PPU-level runtime activation instead of pretending Save Desired applies runtime", () => {
  assert.match(ppuRuntimeActivation, /Activate Desired Configuration/);
  assert.match(ppuRuntimeActivation, /All-Site impact/);
  assert.match(ppuRuntimeActivation, /runtime_apply_supported/);
  assert.match(ppuRuntimeActivation, /Runtime In Sync/);
  assert.match(ppuRuntimeActivation, /Server-authoritative admission gate/);
  assert.doesNotMatch(ppuSiteDesiredCore, /onClick=\{[^}]*restart/i);
});

test("PPU management names the northbound service Plasma Gateway", () => {
  assert.match(ppuSite, /Plasma Gateway Endpoint/);
  assert.match(ppuSite, /Add a Plasma Gateway to the Manager registry/);
  assert.match(ppuSite, /<th>Plasma Gateway<\/th>/);
  assert.doesNotMatch(ppuSite, /<span>Gateway Endpoint<\/span>|<dt>Gateway Endpoint<\/dt>|<th>Gateway<\/th>/);
});

test("PPU network desired state and commissioning are rendered inside PPU/Site management", () => {
  assert.match(ppuSite, /import PpuNetworkConfiguration/);
  assert.match(ppuSite, /<PpuNetworkConfiguration/);
  assert.match(ppuSite, /hasActiveExecution=\{selectedHasActiveExecution\}/);
  assert.match(ppuNetwork, /PPU Network Configuration/);
  assert.match(ppuNetwork, /Save Desired Network/);
  assert.match(ppuNetwork, /Commission Static Network/);
  assert.match(ppuNetwork, /Manager Txn/);
  assert.match(ppuNetwork, /Running <code>eth0<\/code> was not activated/);
});

test("PPU network UI distinguishes Linux Default Gateway from the Plasma Gateway service", () => {
  assert.match(ppuNetwork, /<span>Default Gateway<\/span>/);
  assert.match(ppuNetwork, /aria-label="PPU static default gateway"/);
  assert.match(ppuNetwork, /Default Gateway is the Linux Layer-3 next-hop router/);
  assert.match(ppuNetwork, /It is not the Plasma Gateway service running on this PPU/);
  assert.doesNotMatch(ppuNetwork, /<span>Gateway<\/span>/);
});

test("Browser never sequences the PPU network activation API directly", () => {
  assert.match(registryApi, /getManagerPpuNetwork/);
  assert.match(registryApi, /saveManagerPpuNetwork/);
  assert.match(registryApi, /commissionManagerPpuStaticNetwork/);
  assert.match(registryApi, /\/api\/manager\/registry\/\$\{encodeURIComponent\(alias\)\}\/network/);
  assert.match(registryApi, /\/network-commissioning/);
  assert.match(registryApi, /Idempotency-Key/);
  assert.doesNotMatch(ppuNetwork, /\/api\/settings\/ppu-network\/activation/);
  assert.doesNotMatch(ppuNetwork, /fetch\(/);
  assert.match(ppuNetwork, /one Manager-owned transaction/);
  assert.match(ppuNetwork, /verify the same <code>ppu_id<\/code>/);
});

test("browser registry client exposes registry, network, commissioning, Site desired state, activation, and PPU selection through same-origin BFF", () => {
  assert.match(registryApi, /\/api\/manager\/registry/);
  assert.match(registryApi, /getManagerPpuSites/);
  assert.match(registryApi, /saveManagerPpuSite/);
  assert.match(registryApi, /activateManagerPpuSiteDesired/);
  assert.match(registryApi, /\/sites\/\$\{siteId\}/);
  assert.match(registryApi, /selectManagerPpuForManagedOperations/);
  assert.match(registryApi, /method: "POST"/);
  assert.match(registryApi, /method: "PATCH"/);
  assert.match(registryApi, /method: "DELETE"/);
  assert.doesNotMatch(registryApi, /127\.0\.0\.1:18180/);
});

test("Manager registry BFF remains loopback-only and commissioning is a Manager resource, not generic PPU relay", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /relayManagerRegistryRequest/);
  assert.match(managerBff, /relayManagerPpuAliasRequest/);
  assert.match(managerBff, /relayManagerNetworkCommissioningRequest/);
  assert.match(managerBff, /\/api\/registry\/\$\{encodeURIComponent\(normalizedAlias\)\}\/network-commissioning/);
  assert.match(managerBff, /requireManagedMode = false/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL/);
  assert.doesNotMatch(managerBff, /gateway\$\{targetPath\}.*network-commissioning/);
});

test("registry BFF routes keep desired-state relay, controlled runtime activation, and Manager-owned commissioning explicit", () => {
  assert.match(registryRoute, /export async function GET/);
  assert.match(registryRoute, /export async function POST/);
  assert.doesNotMatch(registryRoute, /export async function PATCH|export async function DELETE/);
  assert.match(registryEntryRoute, /"entry" \| "network" \| "network-commissioning" \| "sites" \| "site" \| "site-activation"/);
  assert.match(registryEntryRoute, /relayManagerPpuAliasRequest\(request, parsed\.alias, "\/api\/settings\/ppu-network"\)/);
  assert.match(registryEntryRoute, /relayManagerPpuAliasRequest\(request, parsed\.alias, "\/api\/settings\/sites"\)/);
  assert.match(registryEntryRoute, /`\/api\/settings\/sites\/\$\{parsed\.siteId\}`/);
  assert.match(registryEntryRoute, /\/api\/settings\/sites\/activation/);
  assert.match(registryEntryRoute, /relayManagerNetworkCommissioningRequest\(request, parsed\.alias\)/);
  assert.match(registryEntryRoute, /export async function GET/);
  assert.match(registryEntryRoute, /export async function POST/);
  assert.match(registryEntryRoute, /export async function PATCH/);
  assert.match(registryEntryRoute, /export async function DELETE/);
});
