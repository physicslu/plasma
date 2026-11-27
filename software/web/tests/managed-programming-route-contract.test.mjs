import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = await readFile(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const gatewayTransport = await readFile(new URL("../app/gateway-transport.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");
const managedConfig = await readFile(new URL("../app/api/manager/ppu/route.ts", import.meta.url), "utf8");
const communicationHealth = await readFile(new URL("../app/fleet/communication-health.ts", import.meta.url), "utf8");
const bootstrapBff = await readFile(new URL("../app/api/manager/bootstrap-bff.ts", import.meta.url), "utf8");
const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
const macConsoleLauncher = await readFile(new URL("../../../packaging/macos/run-console.sh", import.meta.url), "utf8");

test("Control Station routing is always the Manager PPU prefix and legacy Browser routing storage is wiped (U10)", () => {
  assert.match(workspace, /return `\$\{window\.location\.origin\}\/api\/manager\/ppu`/);
  assert.doesNotMatch(workspace, /discoverManagedRouting|localStorage|API_MODE_STORAGE_KEY|storedMode|"standalone"/);
  assert.match(layout, /window\.localStorage\.removeItem\(apiKey\)/);
  assert.match(layout, /window\.localStorage\.removeItem\("plasma-api-mode"\)/);
  assert.match(layout, /window\.sessionStorage\.removeItem\("plasma-production-active-batch-v1"\)/);
  assert.match(layout, /window\.sessionStorage\.removeItem\("plasma-engineering-active-batch-v1"\)/);
});

test("Gateway transport isolates bootstrap reads until WorkspaceSession resolves routing", () => {
  assert.match(gatewayTransport, /let gatewayRoutingResolved = false/);
  assert.match(gatewayTransport, /const gatewayRoutingReady = new Promise/);
  assert.match(gatewayTransport, /const directPath = directGatewayPathname\(url\.pathname\)/);
  assert.match(gatewayTransport, /if \(!gatewayRoutingResolved\) \{/);
  assert.match(gatewayTransport, /if \(isStateChanging\(requestMethod\(currentInput, init\)\)\) return routingUnresolvedResponse\(\)/);
  assert.match(gatewayTransport, /await gatewayRoutingReady/);
  assert.match(gatewayTransport, /const rebasedUrl = `\$\{resolvedGatewayApiBase\}\$\{directPath\}\$\{search\}`/);
  assert.match(workspace, /markGatewayRoutingResolved\(managedApiBase\(\)\);/);
  assert.match(workspace, /const apiBase = hydrated \? managedApiBase\(\) : "";/);
});

test("Managed routing remains authoritative after bootstrap and rebases stale direct Gateway paths", () => {
  // U10: no routing mode; once resolved, every Gateway path is rebased.
  assert.doesNotMatch(gatewayTransport, /GatewayRoutingMode|gatewayRoutingMode|"standalone"/);
  assert.match(gatewayTransport, /\} else if \(resolvedGatewayApiBase\) \{\s*currentInput = rebaseInput\(currentInput, directPath, url\.search\);/);
  assert.doesNotMatch(gatewayTransport, /"\/api\/batches"/);
  assert.doesNotMatch(gatewayTransport, /bearerToken|"Authorization"/);
});

test("Managed Control Station stays fail-closed and cannot switch to a direct Gateway", () => {
  // Unset or "managed" is managed; any other mode is a misconfiguration, never standalone.
  assert.match(managerBff, /if \(mode && mode !== "managed"\) \{\s*throw new Error\("PLASMA_CONTROL_STATION_MODE must be managed when configured"\);/);
  assert.match(managerBff, /export function managerRoutingRequired\(\): true/);
  for (const source of [managerBff, managedConfig, bootstrapBff]) {
    assert.doesNotMatch(source, /managed: false|manager_not_enabled/);
  }
  assert.doesNotMatch(workspace, /apiMode|setApiBase\b|managedPpuAlias|normalized !== managedBase/);
});

test("macOS Control Station declares managed routing intent independently from Browser storage", () => {
  assert.match(macConsoleLauncher, /PLASMA_CONTROL_STATION_MODE="managed"/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /managerRoutingRequired/);
  assert.match(managedConfig, /managed: true/);
  assert.match(managedConfig, /configured: false/);
  assert.match(managedConfig, /configured: true/);
});

test("PMode and EMode keep one shared WorkspaceSession apiBase", () => {
  assert.match(workspace, /const hydrated = useSyncExternalStore\(subscribeNever, \(\) => true, \(\) => false\);/);
  assert.match(workspace, /const apiBase = hydrated \? managedApiBase\(\) : "";/);
  assert.match(workspace, /apiBase,/);
  assert.doesNotMatch(workspace, /ensureEngineeringSession|restartEngineeringSession|programmingImage|pmodOperations/);
});

test("plasma-api carries types only: the Browser has no direct Job, status or Programming Asset client (U10)", () => {
  assert.doesNotMatch(plasmaApi, /fetch\(|"\/api\/jobs"|\/api\/programming-assets|application\/octet-stream/);
});

test("Managed PPU selection is runtime state and no longer requires Console restart", () => {
  assert.match(managerBff, /MANAGED_PPU_SELECTION_COOKIE = "plasma-manager-ppu-alias"/);
  assert.match(managerBff, /requestPpuAlias\(request\)/);
  assert.match(managerBff, /commissionedManagerPpuAliases\(\)/);
  assert.match(managerBff, /if \(commissionedAliases\.length === 1\) return commissionedAliases\[0\]/);
  assert.match(managerBff, /ppuAlias = await resolveManagerPpuAlias\(request\)/);
  assert.match(managedConfig, /export async function POST\(request: Request\)/);
  assert.match(managedConfig, /managerPpuAliasIsCommissioned\(alias\)/);
  assert.match(managedConfig, /Set-Cookie.*managerPpuSelectionCookie\(alias\)/s);
  assert.doesNotMatch(managedConfig, /target_url|NEXT_PUBLIC_PLASMA_API_URL/);
});

test("Browser managed route exposes no PPU endpoint and keeps Manager as alias-to-endpoint owner", () => {
  assert.match(managedConfig, /managerApiBase\(\)/);
  assert.match(managedConfig, /resolveManagerPpuAlias\(request\)/);
  assert.doesNotMatch(managedConfig, /endpoint|target_url|NEXT_PUBLIC_PLASMA_API_URL/);
  assert.match(managedRoute, /MANAGED_BROWSER_PREFIX = "\/api\/manager\/ppu"/);
  assert.match(managedRoute, /relayManagerPpuRequest/);
  assert.doesNotMatch(managedRoute, /target_url|NEXT_PUBLIC_PLASMA_API_URL/);
});

test("BFF preserves only the required security/content/conditional headers and keeps Manager loopback-only", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL must remain loopback-only/);
  assert.match(managerBff, /\["Accept", "Authorization", "Content-Type", "Idempotency-Key", "If-Match"\]/);
  assert.match(managerBff, /MAX_MANAGED_REQUEST_BYTES = 24 \* 1024 \* 1024/);
  assert.doesNotMatch(managerBff, /Set-Cookie.*forwardedHeaders/s);
  assert.doesNotMatch(managerBff, /target_url/);
});

test("managed non-JSON upstream errors remain HTTP failures instead of transport failures", () => {
  assert.match(managerBff, /managed_upstream_non_json/);
  assert.match(managerBff, /response\.status >= 400 \? response\.status : 502/);
  assert.match(communicationHealth, /error instanceof PlasmaApiError && error\.status !== undefined \? "online" : "unreachable"/);
});

test("gateway transport recognizes managed PPU paths and carries no browser credential", () => {
  assert.match(gatewayTransport, /MANAGED_PPU_PREFIX = "\/api\/manager\/ppu"/);
  assert.match(gatewayTransport, /pathname\.startsWith\(`\$\{MANAGED_PPU_PREFIX\}\/`\)/);
  // LOM-P2A-2: write authority is the Manager-held controller credential (G13).
  assert.doesNotMatch(gatewayTransport, /bearerToken|"Authorization"|Idempotency-Key/);
});
