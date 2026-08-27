import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const factory = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const health = await readFile(new URL("../app/fleet/communication-health.ts", import.meta.url), "utf8");

test("PMode renders layered Gateway and PPU health instead of one Connected flag", () => {
  assert.match(factory, /Factory communication health/);
  assert.match(factory, /Gateway ONLINE/);
  assert.match(factory, /Gateway UNREACHABLE/);
  assert.match(factory, /summarizePPUHealth/);
  assert.doesNotMatch(factory, />Connected</);
});

test("Gateway reachability is classified from HTTP response evidence", () => {
  assert.match(health, /error instanceof PlasmaApiError && error\.status !== undefined \? "online" : "unreachable"/);
  assert.match(factory, /setGatewayHealth\(gatewayHealthFromSettled\(results\)\)/);
  assert.match(factory, /setGatewayHealth\(gatewayHealthFromError\(error\)\)/);
});

test("Production readiness is fail-closed when Gateway is not online", () => {
  assert.match(factory, /providerOnline: gatewayHealth === "online" && Boolean\(catalog && !providerError\)/);
});
