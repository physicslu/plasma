import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const loopback = await readFile(new URL("../app/engineering/loopback-test.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../app/engineering/diagnostics-api.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/diagnostics/loopback/route.ts", import.meta.url), "utf8");
const shell = await readFile(new URL("../app/engineering/diagnostics-test-page.tsx", import.meta.url), "utf8");
const css = await readFile(new URL("../app/engineering/loopback-test.css", import.meta.url), "utf8");
const resultCss = await readFile(new URL("../app/engineering/loopback-test-results.css", import.meta.url), "utf8");

test("Diagnostics exposes Loopback Test as an EMode tree child", () => {
  assert.match(engineering, /type DiagnosticsSection = "loopback"/);
  assert.match(engineering, /<LoopbackTest \/>/);
  assert.match(engineering, /engineeringNavTreeGroup/);
  assert.match(engineering, /Loopback Test/);
});

test("loopback path uses endpoint intent and fills every upstream node", () => {
  assert.match(loopback, /endpointIndex: Record<LoopbackEndpoint, number> = \{ ps: 1, pl: 2, ic: 3 \}/);
  assert.match(loopback, /index <= selectedIndex \? "active" : ""/);
  assert.match(loopback, /Web → PS → PL → IC → PL → PS → Web/);
  assert.doesNotMatch(loopback, /Disable/);
  assert.doesNotMatch(loopback, /\bNC\b|\bNO\b/);
});

test("loopback keeps routing internals out of the visible controls", () => {
  assert.match(css, /\.loopbackNode\.active[\s\S]*background: var\(--cyan\)/);
  assert.match(css, /\.loopbackNode \{[\s\S]*background: var\(--panel\)/);
  assert.doesNotMatch(loopback, /relayState|routingState/);
});

test("browser generates deterministic reproducible test payloads", () => {
  for (const required of [
    "PRBS (Pseudo Random Binary Sequence)",
    "Incrementing byte",
    "Walking 1",
    "Walking 0",
    "0x12345678",
    "generatePayload",
    "crc32Hex",
    "window.crypto.randomUUID",
  ]) assert.match(loopback, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("payload length supports single, boundary and range modes", () => {
  assert.match(loopback, /type LengthMode = "single" \| "boundary" \| "range"/);
  assert.match(loopback, /Math\.max\(1, n - 1\), n, n \+ 1/);
  assert.match(loopback, /setBoundary\("1024"\)/);
  assert.match(loopback, /setRangeStart\("64"\)/);
  assert.match(loopback, /setRangeEnd\("4096"\)/);
});

test("Diagnostics Test Page shell is shared while loopback keeps domain controls", () => {
  assert.match(shell, /export function DiagnosticsTestPage/);
  assert.match(shell, /export function DiagnosticsTestCard/);
  assert.match(shell, /export function DiagnosticsTestNotice/);
  assert.doesNotMatch(shell, /LoopbackEndpoint|PRBS|Boundary/);
});

test("Phase 0 PS loopback crosses the Manager pass-through before the PPU", () => {
  assert.match(api, /\/api\/manager\/diagnostics\/loopback/);
  assert.doesNotMatch(api, /\/api\/engineering\/diagnostics\/loopback/);
  assert.match(api, /success\.manager\?\.relay !== "pass-through"/);
  assert.match(api, /manager_relay_unverified/);
  assert.match(managerBff, /PLASMA_MANAGER_API_URL/);
  assert.match(managerBff, /PLASMA_MANAGER_PPU_ALIAS/);
  assert.match(managerBff, /\/api\/ppus\/\$\{encodeURIComponent\(ppuAlias\)\}\/diagnostics\/loopback/);
  assert.match(managerBff, /LOOPBACK_HOSTS/);
  assert.doesNotMatch(managerBff, /NEXT_PUBLIC_PLASMA_API_URL/);
});

test("Phase 0 still executes only the PS production real path", () => {
  assert.match(loopback, /endpoint !== "ps"/);
  assert.match(loopback, /executePsLoopbackCase/);
  assert.match(loopback, /Browser → REST Gateway → Plasma Server → Browser/);
  assert.match(loopback, /does not use MockInterface/);
  assert.match(loopback, /never falls back to Mock/);
  assert.doesNotMatch(loopback, /mock-runtime|MockRuntime|mockRuntime/);
  assert.doesNotMatch(api, /mock-runtime|MockRuntime|mockRuntime/);
  assert.match(loopback, /response\.loopback\.source === "ps"/);
  assert.match(loopback, /firstMismatch\(payload, returned\)/);
});

test("results render observed CRC, RTT and endpoint verification", () => {
  assert.match(loopback, /TX CRC32/);
  assert.match(loopback, /RX CRC32/);
  assert.match(loopback, /PPU RTT/);
  assert.match(loopback, /loopbackResultBadge/);
  assert.match(resultCss, /\.loopbackResultBadge\.pass/);
  assert.match(resultCss, /\.loopbackResultBadge\.fail/);
});
