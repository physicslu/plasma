import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const panel = await readFile(new URL("../app/engineering/openocd-control-plane-test.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../app/engineering/openocd-control-plane-api.ts", import.meta.url), "utf8");
const css = await readFile(new URL("../app/engineering/openocd-control-plane-test.css", import.meta.url), "utf8");
const evidenceCss = await readFile(new URL("../app/engineering/diagnostics-evidence.css", import.meta.url), "utf8");
const managedBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");

test("Diagnostics exposes a separate OpenOCD Control Plane child", () => {
  assert.ok(engineering.includes('type DiagnosticsSection = "loopback" | "openocd"'));
  assert.ok(engineering.includes("OpenOCD Control Plane"));
  assert.ok(engineering.includes("<OpenOcdControlPlaneTest />"));
  assert.ok(panel.includes("EMODE / DIAGNOSTICS / OPENOCD CONTROL PLANE"));
});

test("browser request surface is closed to site and timeout only", () => {
  assert.ok(api.includes("site_id: number"));
  assert.ok(api.includes("timeout_ms: number"));
  assert.doesNotMatch(api, /command:/);
  assert.doesNotMatch(panel, /tcl_command|startup_commands/);
  assert.ok(panel.includes("Browser 無法提交 Tcl command"));
});

test("OpenOCD diagnostic uses the same managed workspace API base and BFF route", () => {
  assert.ok(api.includes("/api/engineering/diagnostics/openocd-control-plane"));
  assert.ok(managedRoute.includes("relayManagerPpuRequest"));
  assert.ok(managedBff.includes("PLASMA_MANAGER_API_URL"));
  assert.ok(managedBff.includes("PLASMA_MANAGER_PPU_ALIAS"));
  assert.ok(managedBff.includes("/api/ppus/${encodeURIComponent(ppuAlias)}/gateway${targetPath}"));
});

test("browser requires explicit software-only evidence and Manager proof", () => {
  assert.ok(api.includes('success.result !== "PASS"'));
  assert.ok(api.includes('success.execution_capability !== "openocd-control-plane-only"'));
  assert.ok(api.includes("success.hardware_runtime_ready !== false"));
  assert.ok(api.includes('success.tcl_rpc_state !== "pass"'));
  assert.ok(api.includes('success.rpc_scope !== "loopback"'));
  assert.ok(api.includes('success.manager?.relay !== "pass-through"'));
  assert.ok(panel.includes("Hardware Runtime Ready"));
  assert.ok(panel.includes("NOT ENABLED"));
  assert.ok(panel.includes("result.not_claimed.map"));
});

test("panel groups evidence into runtime, execution, performance and qualification boundary", () => {
  for (const label of [
    "OpenOCD Control Plane",
    "Runtime ID",
    "Worker Lifecycle",
    "Tcl RPC",
    "RPC Scope",
    "Architecture",
    "Worker Generation",
    "PPU Latency",
    "Manager RTT",
    "Execution Capability",
    "QUALIFICATION BOUNDARY",
  ]) {
    assert.ok(panel.includes(label), `missing evidence label: ${label}`);
  }
  assert.ok(panel.includes("Started → Stopped normally"));
  assert.ok(panel.includes("啟動 → 正常停止"));
  assert.ok(panel.includes('import "./diagnostics-evidence.css"'));
  assert.ok(evidenceCss.includes(".diagnosticsEvidenceSectionGrid"));
  assert.ok(evidenceCss.includes("grid-template-columns: repeat(3, minmax(0, 1fr))"));
  assert.ok(evidenceCss.includes(".diagnosticsEvidenceBoundary"));
  assert.doesNotMatch(css, /diagnosticsEvidenceSection|diagnosticsEvidenceBoundary/);
});
