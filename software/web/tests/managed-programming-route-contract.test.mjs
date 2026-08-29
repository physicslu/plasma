import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = await readFile(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const securityTransport = await readFile(new URL("../app/security-transport.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");
const managedConfig = await readFile(new URL("../app/api/manager/ppu/route.ts", import.meta.url), "utf8");

test("managed deployments migrate legacy direct Gateway selection to the Manager-owned API base", () => {
  assert.match(workspace, /return `\$\{window\.location\.origin\}\/api\/manager\/ppu`/);
  assert.match(workspace, /fetch\("\/api\/manager\/ppu"/);
  assert.match(workspace, /plasma-api-mode/);
  assert.match(workspace, /rawMode === "managed" \|\| rawMode === "standalone"/);
  assert.match(workspace, /mode === "standalone"/);
  assert.match(workspace, /mode === "managed" \|\| await managedRoutingConfigured\(\)/);
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
