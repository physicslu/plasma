import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const factory = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const health = await readFile(new URL("../app/fleet/communication-health.ts", import.meta.url), "utf8");
const readiness = await readFile(new URL("../app/batch-readiness.ts", import.meta.url), "utf8");

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

test("Programming provider absence does not downgrade a reachable PPU to offline", () => {
  assert.match(health, /PPU ONLINE · PROGRAMMING UNAVAILABLE/);
  assert.match(health, /gatewayHealth === "unreachable"[\s\S]*PPU UNKNOWN/);
  assert.doesNotMatch(readiness, /"ppu-offline"/);
  assert.match(readiness, /"programming-unavailable": "PROGRAMMING UNAVAILABLE"/);
  assert.match(readiness, /!input\.providerOnline\) return result\("programming-unavailable"\)/);
});

test("Production dispatch remains fail-closed when Programming provider is unavailable", () => {
  assert.match(factory, /providerOnline: gatewayHealth === "online" && Boolean\(catalog && !providerError\)/);
  assert.match(readiness, /Provider availability is a Programming capability signal, not a PPU/);
});
