import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const overview = await readFile(new URL("../app/engineering/ppu-overview-page.tsx", import.meta.url), "utf8");
const registration = await readFile(new URL("../app/engineering/ppu-registration-page.tsx", import.meta.url), "utf8");
const sitesPage = await readFile(new URL("../app/engineering/ppu-sites-page.tsx", import.meta.url), "utf8");
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
const managerServer = await readFile(new URL("../../python/plasma_manager/server.py", import.meta.url), "utf8");

test("PPU is a first-class EMode object with four functional subpages", () => {
  assert.match(engineering, /\["ppu-sites", "engineering\.ppuSites", "▤"\]/);
  assert.match(engineering, /type PpuSection = "overview" \| "platform" \| "registration" \| "sites"/);
  assert.match(engineering, /aria-label="PPU Management"/);
  assert.match(engineering, /<PpuOverviewPage onNavigate=\{selectPpuSection\} \/>/);
  assert.match(engineering, /<PpuRuntimeDeploymentPage \/>/);
  assert.match(engineering, /<PpuRegistrationPage \/>/);
  assert.match(engineering, /<PpuSitesPage \/>/);
  assert.doesNotMatch(engineering, /<PpuSiteConfiguration \/>/);
});

test("PPU Overview is read-only and summarizes Platform, Registration, Sites, and alerts", () => {
  assert.match(overview, /aria-label="PPU Overview"/);
  assert.match(overview, /PPU Platform Firmware/);
  assert.match(overview, /Bootstrap Version/);
  assert.match(overview, /Runtime Version/);
  assert.match(overview, /Registration/);
  assert.match(overview, /Site summary|PPU Site summary/);
  assert.match(overview, /Alerts/);
  assert.match(overview, /onNavigate\("platform"\)/);
  assert.match(overview, /onNavigate\("registration"\)/);
  assert.match(overview, /onNavigate\("sites"\)/);
  assert.doesNotMatch(overview, /addManagerPpu|setManagerPpuLifecycle|removeManagerPpu|saveManagerPpuSite/);
});

test("Registration owns Console programming admission, not Platform maintenance", () => {
  assert.match(registration, /addManagerPpu/);
  assert.match(registration, /setManagerPpuLifecycle/);
  assert.match(registration, /removeManagerPpu/);
  assert.match(registration, /Validate & Register for Programming/);
  assert.match(registration, /Programming Registration is still pending/);
  assert.match(registration, /Platform maintenance remains a separate lifecycle/);
  assert.match(registration, /Bootstrap maintenance authorization used by Platform Firmware update is a separate Platform security boundary/);
  assert.doesNotMatch(registration, /pairManagerPpuBootstrap|startManagerPpuBootstrapDeployment/);
});

test("Registration keeps Lifecycle, Connectivity, and Health as orthogonal observations", () => {
  assert.match(registration, /Registration Lifecycle/);
  assert.match(registration, /Connectivity/);
  assert.match(registration, /Health/);
  assert.match(registration, /lifecycleState\(entry\)/);
  assert.match(registration, /connectivityState\(fleetView\)/);
  assert.match(registration, /healthState\(fleetView\)/);
  assert.match(ppuUiState, /entry\.lifecycle === "commissioned"/);
  assert.match(ppuUiState, /fleetView\.transport_state === "unreachable"/);
  assert.match(ppuUiState, /fleetView\.identity_conflict/);
  assert.match(ppuUiState, /fleetView\.degraded/);
});

test("programming Registration remains fail-closed on validation prerequisites", () => {
  for (const prerequisite of [
    "Observation current",
    "Transport reachable",
    "Execution ready",
    "No identity conflict",
    "Not degraded",
  ]) {
    assert.match(ppuUiState, new RegExp(prerequisite));
  }
  assert.match(registration, /aria-label="Registration prerequisites"/);
  assert.match(registration, /Failing prerequisites:/);
  assert.match(registration, /selectedPrerequisites\.map/);
  assert.match(registration, /disabled=\{!registryMutable \|\| !selectedCanValidate \|\| busyAction !== null\}/);
});

test("only registered PPUs can be selected for managed programming operations", () => {
  assert.match(registryApi, /selectManagerPpuForManagedOperations/);
  assert.match(registration, /selectedEntry\.lifecycle !== "commissioned"/);
  assert.match(registration, /Use for Managed Operations/);
  assert.match(managedSelectionRoute, /managerPpuAliasIsCommissioned\(alias\)/);
  assert.match(managedSelectionRoute, /managerPpuSelectionCookie\(alias\)/);
  assert.match(managerBff, /resolveManagerPpuAlias\(request\)/);
});

test("Sites are PPU child resources and operational configuration is Registration-gated", () => {
  assert.match(sitesPage, /Programming Sites are child resources of a PPU/);
  assert.match(sitesPage, /const registered = selectedEntry\?\.lifecycle === "commissioned"/);
  assert.match(sitesPage, /\{registered \? \(/);
  assert.match(sitesPage, /<PpuSiteDesiredConfiguration/);
  assert.match(sitesPage, /Registration required/);
  assert.match(sitesPage, /Platform Firmware inspection and maintenance remain available from Platform while Sites are locked/);
  assert.match(managerServer, /if self\.command == "POST" and self\._registry_lifecycle\(alias\) != REGISTRY_LIFECYCLE_COMMISSIONED/);
  assert.match(managerServer, /PPU must complete Validate & Enable before Manager write operations/);
});

test("PPU topology remains observed while Site desired configuration is PPU-owned and writable after Registration", () => {
  assert.match(sitesPage, /fleetForEntry/);
  assert.match(sitesPage, /selectedFleet\?\.topology\.site_count/);
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
});

test("Site UI separates browser Draft, persisted Desired, and observed Runtime without hard-coding topology", () => {
  assert.match(ppuSiteDesiredCore, />Draft</);
  assert.match(ppuSiteDesiredCore, />Desired</);
  assert.match(ppuSiteDesiredCore, />Runtime</);
  assert.match(ppuSiteDesiredCore, /Unsaved Draft/);
  assert.match(ppuSiteDesiredCore, /Saving updates Desired configuration only; Runtime remains separately reconciled/);
  assert.match(ppuSiteDesiredCore, /Topology is discovered from the PPU/);
  assert.doesNotMatch(ppuSiteDesiredCore, /Array\(8\)|SITE8|site_count\s*===\s*8/);
  assert.doesNotMatch(ppuSiteDesiredCore, /Programming Channel|Channel Configuration|CH[1-8]/);
});

test("controlled PPU-level runtime activation remains explicit", () => {
  assert.match(ppuRuntimeActivation, /Activate Desired Configuration/);
  assert.match(ppuRuntimeActivation, /All-Site impact/);
  assert.match(ppuRuntimeActivation, /runtime_apply_supported/);
  assert.match(ppuRuntimeActivation, /Runtime In Sync/);
  assert.match(ppuRuntimeActivation, /Server-authoritative admission gate/);
});

test("network commissioning is preserved as a Registration/onboarding operation", () => {
  assert.match(registration, /import PpuNetworkConfiguration/);
  assert.match(registration, /selectedEntry\.lifecycle === "commissioned"/);
  assert.match(registration, /<PpuNetworkConfiguration entry=\{selectedEntry\} hasActiveExecution=\{selectedHasActiveExecution\} \/>/);
  assert.match(registration, /Operational network commissioning remains locked until programming Registration is complete/);
  assert.match(ppuNetwork, /PPU Network Configuration/);
  assert.match(ppuNetwork, /Save Desired Network/);
  assert.match(ppuNetwork, /Commission Static Network/);
  assert.match(managerServer, /PPU must complete Validate & Enable before network commissioning/);
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
  assert.match(registryApi, /\/network-commissioning/);
  assert.match(registryApi, /Idempotency-Key/);
  assert.doesNotMatch(ppuNetwork, /\/api\/settings\/ppu-network\/activation/);
  assert.doesNotMatch(ppuNetwork, /fetch\(/);
  assert.match(ppuNetwork, /one Manager-owned transaction/);
});

test("browser registry client exposes bounded inventory, network, Site, activation, and selection APIs", () => {
  assert.match(registryApi, /\/api\/manager\/registry/);
  assert.match(registryApi, /getManagerPpuSites/);
  assert.match(registryApi, /saveManagerPpuSite/);
  assert.match(registryApi, /activateManagerPpuSiteDesired/);
  assert.match(registryApi, /selectManagerPpuForManagedOperations/);
  assert.match(registryApi, /method: "POST"/);
  assert.match(registryApi, /method: "PATCH"/);
  assert.match(registryApi, /method: "DELETE"/);
  assert.doesNotMatch(registryApi, /127\.0\.0\.1:18180/);
});

test("Manager registry BFF remains loopback-only and commissioning remains a Manager resource", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /relayManagerRegistryRequest/);
  assert.match(managerBff, /relayManagerPpuAliasRequest/);
  assert.match(managerBff, /relayManagerNetworkCommissioningRequest/);
  assert.match(managerBff, /requireManagedMode = false/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL/);
});

test("registry BFF keeps desired-state relay, runtime activation, commissioning, and Bootstrap explicit", () => {
  assert.match(registryRoute, /export async function GET/);
  assert.match(registryRoute, /export async function POST/);
  assert.match(registryEntryRoute, /"entry" \| "network" \| "network-commissioning" \| "sites" \| "site" \| "site-activation" \| "bootstrap"/);
  assert.match(registryEntryRoute, /relayManagerPpuAliasRequest\(request, parsed\.alias, "\/api\/settings\/ppu-network"\)/);
  assert.match(registryEntryRoute, /relayManagerPpuAliasRequest\(request, parsed\.alias, "\/api\/settings\/sites"\)/);
  assert.match(registryEntryRoute, /\/api\/settings\/sites\/activation/);
  assert.match(registryEntryRoute, /relayManagerNetworkCommissioningRequest\(request, parsed\.alias\)/);
  assert.match(registryEntryRoute, /relayManagerBootstrapRequest/);
});
