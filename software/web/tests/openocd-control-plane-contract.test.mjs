import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const panel = await readFile(new URL("../app/engineering/openocd-control-plane-test.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../app/engineering/openocd-control-plane-api.ts", import.meta.url), "utf8");
const css = await readFile(new URL("../app/engineering/openocd-control-plane-test.css", import.meta.url), "utf8");
const managedBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
const managedRoute = await readFile(new URL("../app/api/manager/ppu/[...path]/route.ts", import.meta.url), "utf8");

test("Diagnostics exposes a separate OpenOCD Control Plane child", () => {
  assert.match(engineering, /type DiagnosticsSection = "loopback" \\| "openocd"/);
  assert.match(engineering, /OpenOCD Control Plane/);
  assert.match(engineering, /<OpenOcdControlPlaneTest \\/>/);
  assert.match(panel, /EMODE \\/ DIAGNOSTICS \\/ OPENOCD CONTROL PLANE/);
});

test("browser request surface is closed to site and timeout only", () => {
  assert.match(api, /site_id: number/);
  assert.match(api, /timeout_ms: number/);
  assert.doesNotMatch(api, /command:/);
  assert.doesNotMatch(panel, /tcl_command|startup_commands/);
  assert.match(panel, /Browser 無法提交 Tcl command/);
});

test("OpenOCD diagnostic uses the same managed workspace API base and BFF route", () => {
  assert.match(api, /fetch\\\\\(`\\$\\{apiBase\\}\\/api\\/engineering\\/diagnostics\\/openocd-control-plane/);
  assert.match(managedRoute, /relayManagerPpuRequest/);
  assert.match(managedBff, /PLASMA_MANAGER_API_URL/);
  assert.match(managedBff, /PLASMA_MANAGER_PPU_ALIAS/);
  assert.ok(managedBff.includes("/api/ppus/${encodeURIComponent(ppuAlias)}/gateway${targetPath}"));
});

test("browser requires explicit software-only evidence and Manager proof", () => {
  assert.match(api, /success\\.result !== "PASS"/);
  assert.match(api, /success\\.execution_capability !== "openocd-control-plane-only"/);
  assert.match(api, /success\\.hardware_runtime_ready !== false/);
  assert.match(api, /success\\.tcl_rpc_state !== "pass"/);
  assert.match(api, /success\\.rpc_scope !== "loopback"/);
  assert.match(api, /success\\.manager\\?\\.relay !== "pass-through"/);
  assert.match(panel, /Hardware Runtime Ready/);
  assert.match(panel, />NO</);
});

test("panel presents process, RPC, architecture, latency and capability evidence", () => {
  for (const label of [
    "OpenOCD Control Plane",
    "OpenOCD",
    "Process",
    "Tcl RPC",
    "RPC Scope",
    "Architecture",
    "Worker Generation",
    "PPU Latency",
    "Manager RTT",
    "Capability",
  ]) {
    assert.match(panel, new RegExp(label));
  }
  assert.match(css, /\\.openocdControlPlaneGrid/);
});
