import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = await readFile(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const securityTransport = await readFile(new URL("../app/security-transport.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");
const managedConfig = await readFile(new URL("../app/api/manager/ppu/route.ts", import.meta.url), "utf8");
const macConsoleLauncher = await readFile(new URL("../../../packaging/macos/run-console.sh", import.meta.url), "utf8");

test("Control Station bootstrap makes BFF managed discovery authoritative over legacy localStorage", () => {
  assert.match(workspace, /return `\$\{window\.location\.origin\}\/api\/manager\/ppu`/);
  assert.match(workspace, /const discovery = await discoverManagedRouting\(\)/);
  assert.match(workspace, /if \(discovery\?\.managed === true\)/);
  assert.match(workspace, /nextMode = "managed"/);
  assert.match(workspace, /window\.localStorage\.setItem\(API_MODE_STORAGE_KEY, nextMode\)/);
  assert.doesNotMatch(workspace, /if \(storedMode === "standalone"\)/);
});

test("Gateway transport isolates bootstrap reads until WorkspaceSession resolves routing", () => {
  assert.match(securityTransport, /let gatewayRoutingResolved = false/);
  assert.match(securityTransport, /const gatewayRoutingReady = new Promise/);
  assert.match(securityTransport, /let directPath = directGatewayPathname\(url\.pathname\)/);
  assert.match(securityTransport, /if \(!gatewayRoutingResolved && directPath !== null\)/);
  assert.match(securityTransport, /if \(isStateChanging\(unresolvedMethod\)\) return routingUnresolvedResponse\(\)/);
  assert.match(securityTransport, /await gatewayRoutingReady/);
  assert.match(securityTransport, /const rebasedUrl = `\$\{resolvedGatewayApiBase\}\$\{directPath\}\$\{search\}`/);
  assert.match(workspace, /markGatewayRoutingResolved\(saved, nextMode\);\s*setHydrated\(true\)/);
  assert.match(workspace, /fetch\("\/api\/manager\/ppu"/);
});

test("Managed routing remains authoritative after bootstrap and rebases stale direct Gateway paths", () => {
  assert.match(securityTransport, /type GatewayRoutingMode = "managed" \| "standalone"/);
  assert.match(securityTransport, /gatewayRoutingMode === "managed"/);
  assert.match(securityTransport, /resolvedGatewayApiBase/);
  assert.match(securityTransport, /currentInput = rebaseInput\(currentInput, directPath, url\.search\)/);
  assert.match(securityTransport, /url\.origin === new URL\(resolvedGatewayApiBase\)\.origin/);
});

test("Managed Control Station stays fail-closed and cannot switch to a direct Gateway", () => {
  assert.match(workspace, /discovery === null && storedMode === "managed"/);
  assert.match(workspace, /apiMode === "managed" && normalized !== managedBase/);
  assert.match(workspace, /Managed Control Station routing is locked to the selected Manager PPU/);
  assert.match(workspace, /apiMode,/);
  assert.match(workspace, /managedPpuAlias,/);
});

test("macOS Control Station declares managed routing intent independently from Browser storage", () => {
  assert.match(macConsoleLauncher, /PLASMA_CONTROL_STATION_MODE="managed"/);
  assert.match(managerBff, /PLASMA_CONTROL_STATION_MODE/);
  assert.match(managerBff, /managerRoutingRequired/);
  assert.match(managedConfig, /managed: managedRequired/);
  assert.match(managedConfig, /configured: false/);
  assert.match(managedConfig, /configured: true/);
});

test("PMode and EMode keep one shared WorkspaceSession apiBase", () => {
  assert.match(workspace, /const \[apiBase, setApiBaseState\] = useState\(DEFAULT_API_BASE\)/);
  assert.match(workspace, /apiBase,/);
  assert.match(workspace, /ensureEngineeringSession/);
  assert.match(workspace, /restartEngineeringSession/);
});

test("Programming APIs continue to use the shared apiBase for jobs, status, cache and binary Image upload", () => {
  assert.match(plasmaApi, /fetch\(`\$\{apiBase\}\$\{path\}`/);
  assert.match(plasmaApi, /\/api\/programming-assets\/check/);
  assert.match(plasmaApi, /Content-Type": "application\/octet-stream"/);
  assert.match(plasmaApi, /body: file/);
  assert.match(plasmaApi, /body\.asset_sha256 = fingerprint\.asset_sha256/);
  assert.match(plasmaApi, /"\/api\/jobs"/);
});

test("Browser managed route exposes no PPU endpoint and always resolves the configured Manager alias", () => {
  assert.match(managedConfig, /managerApiBase\(\)/);
  assert.match(managedConfig, /managerPpuAlias\(\)/);
  assert.doesNotMatch(managedConfig, /endpoint|target_url|NEXT_PUBLIC_PLASMA_API_URL/);
  assert.match(managedRoute, /MANAGED_BROWSER_PREFIX = "\/api\/manager\/ppu"/);
  assert.match(managedRoute, /relayManagerPpuRequest/);
  assert.doesNotMatch(managedRoute, /target_url|NEXT_PUBLIC_PLASMA_API_URL/);
});

test("BFF preserves only the required security/content headers and keeps Manager loopback-only", () => {
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL must remain loopback-only/);
  assert.match(managerBff, /\["Accept", "Authorization", "Content-Type", "Idempotency-Key"\]/);
  assert.match(managerBff, /MAX_MANAGED_REQUEST_BYTES = 24 \* 1024 \* 1024/);
  assert.doesNotMatch(managerBff, /Cookie|Set-Cookie|target_url/);
});

test("security transport recognizes managed PPU paths and keeps idempotency protection", () => {
  assert.match(securityTransport, /MANAGED_PPU_PREFIX = "\/api\/manager\/ppu"/);
  assert.match(securityTransport, /pathname\.startsWith\(`\$\{MANAGED_PPU_PREFIX\}\/`\)/);
  assert.match(securityTransport, /headers\.set\("Authorization", `Bearer \$\{bearerToken\}`\)/);
  assert.match(securityTransport, /headers\.set\("Idempotency-Key", commandIdFor\(identity\)\)/);
});
