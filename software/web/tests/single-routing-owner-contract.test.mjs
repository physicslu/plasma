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

  assert.match(workspace, /const API_STORAGE_KEY = "plasma-api-base"/);
  assert.match(workspace, /markGatewayRoutingResolved\(saved, nextMode\)/);
  assert.match(devicesPage, /useWorkspaceSession\(\)/);
  assert.match(devicesPage, /<ICSelector usage="lookup" apiBase=\{apiBase\}/);
  assert.doesNotMatch(deviceApi, /localStorage/);
  assert.doesNotMatch(deviceApi, /DEFAULT_API_BASE/);
  assert.match(deviceApi, /apiBase: string/);
  assert.doesNotMatch(picker, /configuredDeviceApiBase/);
  assert.match(picker, /apiBase: string/);
  assert.doesNotMatch(selector, /configuredDeviceApiBase/);
  assert.match(selector, /apiBase: string/);
});

test("Managed transport rebases canonical Gateway paths after routing resolves", async () => {
  const transport = await source("../app/security-transport.ts");

  assert.match(transport, /type GatewayRoutingMode = "managed" \| "standalone"/);
  assert.match(transport, /gatewayRoutingMode === "managed"/);
  assert.match(transport, /directGatewayPathname\(url\.pathname\)/);
  assert.match(transport, /rebaseInput\(currentInput, directPath, url\.search\)/);
  assert.match(transport, /url\.origin === new URL\(resolvedGatewayApiBase\)\.origin/);
  assert.match(transport, /const trimmed = apiBase\.trim\(\)/);
  assert.match(transport, /: window\.location\.origin/);
  assert.doesNotMatch(transport, /savedGatewayApiBase/);
});

test("product entry retires the legacy Single PPU Programming UI", async () => {
  const [rootPage, nextConfig, renderMain] = await Promise.all([
    source("../app/page.tsx"),
    source("../next.config.ts"),
    source("../render/main.tsx"),
  ]);

  assert.match(rootPage, /redirect\("\/demo"\)/);
  assert.doesNotMatch(rootPage, /SiteMatrixHome|site-matrix-home|PPU CONTROL|SITE MATRIX/);
  assert.match(nextConfig, /source:\s*"\/ppu"/);
  assert.match(nextConfig, /destination:\s*"\/engineering"/);
  assert.match(nextConfig, /permanent:\s*false/);
  assert.match(renderMain, /function RetiredPpuConsoleRoute\(\)/);
  assert.match(renderMain, /replaceRoute\("\/engineering"\)/);
  assert.match(renderMain, /pathname === "\/ppu"/);
  assert.doesNotMatch(renderMain, /import PPUConsole/);
});
