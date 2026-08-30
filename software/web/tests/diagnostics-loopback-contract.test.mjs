import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const loopback = await readFile(new URL("../app/engineering/loopback-test.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../app/engineering/diagnostics-api.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/diagnostics/loopback/route.ts", import.meta.url), "utf8");
const managedBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");
const vite = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
const shell = await readFile(new URL("../app/engineering/diagnostics-test-page.tsx", import.meta.url), "utf8");
const css = await readFile(new URL("../app/engineering/loopback-test.css", import.meta.url), "utf8");
const resultCss = await readFile(new URL("../app/engineering/loopback-test-results.css", import.meta.url), "utf8");

test("Diagnostics exposes Loopback Test as an EMode tree child", () => {
  assert.match(engineering, /type DiagnosticsSection = "loopback"/);
  assert.match(engineering, /<LoopbackTest \/>/);
  assert.match(engineering, /engineeringNavTreeGroup/);
  assert.match(engineering, /Loopback Test/);
});

test("loopback path keeps Control Console and Plasma Manager fixed while endpoints fill upstream nodes", () => {
  assert.match(loopback, /endpointIndex: Record<LoopbackEndpoint, number> = \{ ps: 2, pl: 3, ic: 4 \}/);
  assert.match(loopback, /\{ label: "CONTROL CONSOLE", detail: "Operator UI" \}/);
  assert.match(loopback, /\{ label: "PLASMA MANAGER", detail: "Fleet control plane" \}/);
  assert.match(loopback, /\{ label: "PS", detail: "Processing System", endpoint: "ps" \}/);
  assert.match(loopback, /\{ label: "PL", detail: "Programmable Logic", endpoint: "pl" \}/);
  assert.match(loopback, /\{ label: "IC", detail: "Diagnostic FW", endpoint: "ic" \}/);
  assert.match(loopback, /index <= selectedIndex \? "active" : ""/);
  assert.match(loopback, /Control Console → Plasma Manager → PS → PL → IC → PL → PS → Plasma Manager → Control Console/);
  assert.doesNotMatch(loopback, /endpoint: "manager"|endpoint: "control-console"/);
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

test("Manager BFF namespace stays in Vinext and receives alias binding", () => {
  assert.ok(vite.includes('"^/api/(?!fleet(?:/|$))(?!manager(?:/|$))"'));
  assert.match(vite, /target: "http:\/\/127\.0\.0\.1:18080"/);
  assert.match(vite, /PLASMA_MANAGER_PPU_ALIAS:\s*process\.env\.PLASMA_MANAGER_PPU_ALIAS\s*\?\?\s*""/);
});

test("PS loopback uses the same workspace API base and shared Manager BFF relay as Programming", () => {
  assert.match(api, /fetch\(`\$\{apiBase\}\/api\/engineering\/diagnostics\/loopback`/);
  assert.doesNotMatch(api, /fetch\("\/api\/manager\/diagnostics\/loopback"/);
  assert.match(api, /success\.manager\?\.relay !== "pass-through"/);
  assert.match(api, /manager_relay_unverified/);
  assert.match(managerBff, /relayManagerPpuRequest/);
  assert.match(managerBff, /\/api\/engineering\/diagnostics\/loopback/);
  assert.match(managedRoute, /relayManagerPpuRequest/);
  assert.match(managedBff, /PLASMA_MANAGER_API_URL/);
  assert.match(managedBff, /PLASMA_MANAGER_PPU_ALIAS/);
  assert.match(managedBff, /\/api\/ppus\/\$\{encodeURIComponent\(ppuAlias\)\}\/gateway\$\{targetPath\}/);
  assert.match(managedBff, /Authorization/);
  assert.match(managedBff, /Idempotency-Key/);
  assert.doesNotMatch(managedBff, /NEXT_PUBLIC_PLASMA_API_URL/);
  assert.match(loopback, /Control Console \(Browser\) → Web BFF → Plasma Manager → PPU REST Gateway → Plasma Server → PS/);
});

test("Phase 0 still executes only the PS production real path", () => {
  assert.match(loopback, /endpoint !== "ps"/);
  assert.match(loopback, /executePsLoopbackCase/);
  assert.match(loopback, /does not use MockInterface/);
  assert.match(loopback, /never falls back to Mock/);
  assert.doesNotMatch(loopback, /mock-runtime|MockRuntime|mockRuntime/);
  assert.doesNotMatch(api, /mock-runtime|MockRuntime|mockRuntime/);
  assert.match(loopback, /response\.loopback\.source === "ps"/);
  assert.match(loopback, /firstMismatch\(payload, returned\)/);
});

test("results render observed CRC, Manager RTT, PPU RTT and endpoint verification", () => {
  assert.match(loopback, /TX CRC32/);
  assert.match(loopback, /RX CRC32/);
  assert.match(loopback, /Manager RTT/);
  assert.match(loopback, /PPU RTT/);
  assert.match(loopback, /loopbackResultBadge/);
  assert.match(resultCss, /\.loopbackResultBadge\.pass/);
  assert.match(resultCss, /\.loopbackResultBadge\.fail/);
});
