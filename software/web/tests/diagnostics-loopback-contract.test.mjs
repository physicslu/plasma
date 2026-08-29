import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const loopback = await readFile(new URL("../app/engineering/loopback-test.tsx", import.meta.url), "utf8");
const shell = await readFile(new URL("../app/engineering/diagnostics-test-page.tsx", import.meta.url), "utf8");
const css = await readFile(new URL("../app/engineering/loopback-test.css", import.meta.url), "utf8");

test("Diagnostics exposes Loopback Test as an EMode tree child", () => {
  assert.match(engineering, /type DiagnosticsSection = "loopback"/);
  assert.match(engineering, /<LoopbackTest \/>/);
  assert.match(engineering, /engineeringNavTreeGroup/);
  assert.match(engineering, /Loopback Test/);
});

test("loopback path uses endpoint intent and fills every upstream node", () => {
  assert.match(loopback, /type LoopbackEndpoint = "ps" \| "pl" \| "ic"/);
  assert.match(loopback, /endpointIndex: Record<LoopbackEndpoint, number> = \{ ps: 1, pl: 2, ic: 3 \}/);
  assert.match(loopback, /index <= selectedIndex \? "active" : ""/);
  assert.match(loopback, /Web → PS → PL → IC → PL → PS → Web/);
  assert.doesNotMatch(loopback, /Disable/);
});

test("loopback V1 keeps relay routing details out of the visible path controls", () => {
  assert.match(loopback, /Low-level relay \/ routing state is derived by the system/);
  assert.match(css, /\.loopbackNode\.active[\s\S]*background: var\(--cyan\)/);
  assert.match(css, /\.loopbackNode \{[\s\S]*background: var\(--panel\)/);
});

test("loopback data contract is deterministic and reproducible", () => {
  for (const required of [
    "PRBS (Pseudo Random Binary Sequence)",
    "Incrementing byte",
    "Walking 1",
    "Walking 0",
    "0x12345678",
    "PL: RX[i] = TX[i] XOR 0x55",
    "IC: RX[i] = TX[i] XOR 0xFF",
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

test("V1 does not fake real-path execution results", () => {
  assert.doesNotMatch(loopback, /fetch\(/);
  assert.doesNotMatch(loopback, /mock-runtime|MockRuntime|mockRuntime/);
  assert.match(loopback, /className="primary" disabled/);
  assert.match(loopback, /does not fabricate PASS \/ FAIL results/);
  assert.match(loopback, /No real-path test has been executed yet/);
});
