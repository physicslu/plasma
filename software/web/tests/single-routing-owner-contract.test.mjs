import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("WorkspaceSession remains the authoritative browser routing owner", async () => {
  const [workspace, devicesPage, deviceApi, picker, selector] = await Promise.all([
    source("../app/workspace-session.tsx"),
    source("../app/devices/page.tsx"),
    source("../app/device-catalog-api.ts"),
    source("../app/devices/ic-picker-field.tsx"),
    source("../app/devices/ic-selector.tsx"),
  ]);

  // U10: the routing target is always the same-origin Manager PPU prefix.
  assert.match(workspace, /return `\$\{window\.location\.origin\}\/api\/manager\/ppu`;/);
  assert.match(workspace, /markGatewayRoutingResolved\(managed\);/);
  assert.doesNotMatch(workspace, /localStorage|API_STORAGE_KEY|apiMode|setApiBase\b|"standalone"/);
  assert.match(devicesPage, /useWorkspaceSession\(\)/);
  // PR-C2: the Device Selector is Manager-owned and same-origin (Manager BFF);
  // it never follows the Gateway apiBase or the managed PPU relay.
  assert.match(devicesPage, /<ICSelector usage="lookup" \/>/);
  assert.doesNotMatch(deviceApi, /localStorage/);
  assert.doesNotMatch(deviceApi, /DEFAULT_API_BASE/);
  assert.doesNotMatch(deviceApi, /apiBase: string/);
  assert.match(deviceApi, /DEVICE_SELECTOR_PATH = "\/api\/manager\/devices\/search"/);
  assert.doesNotMatch(picker, /configuredDeviceApiBase/);
  assert.doesNotMatch(picker, /apiBase/);
  assert.doesNotMatch(selector, /configuredDeviceApiBase/);
  assert.doesNotMatch(selector, /apiBase/);
});

test("Managed transport rebases canonical Gateway paths after routing resolves", async () => {
  const transport = await source("../app/gateway-transport.ts");

  // U10: there is no routing mode; every Gateway path is rebased onto the Manager prefix.
  assert.doesNotMatch(transport, /GatewayRoutingMode|gatewayRoutingMode|"standalone"/);
  assert.match(transport, /const MANAGED_PPU_PREFIX = "\/api\/manager\/ppu";/);
  assert.match(transport, /export function markGatewayRoutingResolved\(apiBase: string\): void/);
  assert.doesNotMatch(transport, /"\/api\/batches"/);
  assert.match(transport, /directGatewayPathname\(url\.pathname\)/);
  assert.match(transport, /rebaseInput\(currentInput, directPath, url\.search\)/);
  assert.doesNotMatch(transport, /bearerToken|"Authorization"/);
  assert.match(transport, /const trimmed = apiBase\.trim\(\)/);
  assert.match(transport, /: window\.location\.origin/);
  assert.doesNotMatch(transport, /savedGatewayApiBase/);
});

test("product entry retires the legacy Single PPU Programming UI", async () => {
  const [rootPage, nextConfig, packageJson] = await Promise.all([
    source("../app/page.tsx"),
    source("../next.config.ts"),
    source("../package.json"),
  ]);

  assert.match(rootPage, /redirect\("\/demo"\)/);
  assert.doesNotMatch(rootPage, /SiteMatrixHome|site-matrix-home|PPU CONTROL|SITE MATRIX/);
  assert.match(nextConfig, /source:\s*"\/ppu"/);
  assert.match(nextConfig, /destination:\s*"\/engineering"/);
  assert.match(nextConfig, /permanent:\s*false/);
  // U10: the standalone static Render SPA (render/, build:render) is retired.
  assert.doesNotMatch(packageJson, /build:render|render\/vite\.config/);
});

test("no Console source keeps a standalone routing mode, Gateway URL or PPU-local Batch client (U10)", async () => {
  const appRoot = new URL("../app/", import.meta.url);
  const files = (await fs.readdir(appRoot, { recursive: true }))
    .filter(name => /\.(ts|tsx|mjs)$/.test(name));
  assert.ok(files.length > 0);
  for (const name of files) {
    const text = await fs.readFile(new URL(name, appRoot), "utf8");
    assert.doesNotMatch(text, /\/api\/batches/, `${name} must not call the PPU-local Batch API`);
    assert.doesNotMatch(text, /NEXT_PUBLIC_PLASMA_API_URL|PLASMA_GATEWAY_PROXY_URL/, `${name} must not configure a Gateway URL`);
    assert.doesNotMatch(text, /\bapiMode\b|setApiBase\b|StandaloneProgrammingWorkspace/, `${name} must not keep a standalone mode`);
    assert.doesNotMatch(text, /managed: false|manager_not_enabled/, `${name} must not report a non-managed Console`);
  }
  const vite = await source("../vite.config.ts");
  assert.doesNotMatch(vite, /proxy:|PLASMA_GATEWAY_PROXY_URL/);
});
