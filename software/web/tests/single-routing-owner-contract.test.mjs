import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("WorkspaceSession remains the authoritative browser routing owner", async () => {
  const [workspace, rootPage, devicesPage, deviceApi, picker, selector] = await Promise.all([
    source("../app/workspace-session.tsx"),
    source("../app/page.tsx"),
    source("../app/devices/page.tsx"),
    source("../app/device-catalog-api.ts"),
    source("../app/devices/ic-picker-field.tsx"),
    source("../app/devices/ic-selector.tsx"),
  ]);

  assert.match(workspace, /const API_STORAGE_KEY = "plasma-api-base"/);
  assert.match(workspace, /markGatewayRoutingResolved\(saved, nextMode\)/);
  assert.match(rootPage, /useWorkspaceSession\(\)/);
  assert.doesNotMatch(rootPage, /DEFAULT_API_BASE/);
  assert.doesNotMatch(rootPage, /normalizeApiBase/);
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
  assert.doesNotMatch(transport, /savedGatewayApiBase/);
});

test("Managed Site Matrix exposes no editable direct Gateway control", async () => {
  const [rootPage, routingCss] = await Promise.all([
    source("../app/page.tsx"),
    source("../app/site-matrix-routing.css"),
  ]);

  assert.match(rootPage, /data-site-matrix-routing-mode=\{apiMode\}/);
  assert.match(rootPage, /Managed routing · Plasma Manager/);
  assert.match(routingCss, /\[data-site-matrix-routing-mode="managed"\] \.connection input/);
  assert.match(routingCss, /\[data-site-matrix-routing-mode="managed"\] \.connection button/);
  assert.match(routingCss, /Manager-owned route/);
});
