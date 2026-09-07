import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("Engineering Programming separates PPU liveness from provider availability", () => {
  assert.match(workspace, /await getGatewayLiveness\(apiBase, configuredGatewayPolicy\.current\.ppu_request_timeout_ms\)/);
  assert.match(workspace, /setConnection\(ppuReachable \? "online" : "offline"\)/);
  assert.match(workspace, /\[PPU\] ONLINE · Programming unavailable/);
  assert.match(workspace, /\[ENGINEERING\] Programming unavailable/);
  assert.doesNotMatch(workspace, /\[ENGINEERING\] Provider unavailable/);
});

test("Programming remains blocked when the provider catalog is unavailable", () => {
  assert.match(workspace, /providerOnline: connection === "online" && Boolean\(catalog\)/);
  assert.match(workspace, /programmingUnavailableLabel/);
});
