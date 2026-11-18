import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

// OPF S5 / PR-C2: Console Device Selector consumers migrate to Plasma Manager.
test("Console Device Selector calls the same-origin Manager BFF, not a PPU Gateway", async () => {
  const [api, transport, route, bff] = await Promise.all([
    source("../app/device-catalog-api.ts"),
    source("../app/gateway-transport.ts"),
    source("../app/api/manager/devices/search/route.ts"),
    source("../app/api/manager/manager-bff.ts"),
  ]);
  assert.match(api, /fetch\(`\$\{DEVICE_SELECTOR_PATH\}\?\$\{params\.toString\(\)\}`/);
  assert.doesNotMatch(api, /\$\{apiBase\}\/api\/devices\/search/);
  assert.doesNotMatch(transport, /"\/api\/devices\/search"/);
  assert.match(route, /export async function GET/);
  assert.doesNotMatch(route, /export async function (POST|PUT|PATCH|DELETE)/);
  assert.match(bff, /relayManagerRequest\(request, `\/api\/devices\/search\$\{incoming\.search\}`, false\)/);
  const relay = bff.match(/export async function relayManagerDeviceSearchRequest[\s\S]*?\n}\n/)?.[0] ?? "";
  assert.ok(relay, "Manager Device Selector relay must exist");
  assert.doesNotMatch(relay, /\/gateway/);
  assert.doesNotMatch(relay, /resolveManagerPpuAlias/);
});

test("Manager no longer relays Device Selector queries to a PPU", async () => {
  const manager = await source("../../python/plasma_manager/server.py");
  const managed = manager.match(/_MANAGED_GET_PATTERNS = tuple\([\s\S]*?\n\)\n/)?.[0] ?? "";
  assert.ok(managed, "managed PPU GET allow-list must exist");
  assert.doesNotMatch(managed, /devices\/search/);
  assert.match(manager, /DEVICE_SEARCH_ROUTE = "\/api\/devices\/search"/);
});
