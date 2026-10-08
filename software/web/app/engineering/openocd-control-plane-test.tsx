"use client";

import { useState } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import { DiagnosticsTestCard, DiagnosticsTestNotice, DiagnosticsTestPage } from "./diagnostics-test-page";
import { executeOpenOcdControlPlane, type OpenOcdControlPlaneResponse } from "./openocd-control-plane-api";
import "./diagnostics-test-page.css";
import "./openocd-control-plane-test.css";

export default function OpenOcdControlPlaneTest() {
  const { locale } = useI18n();
  const { apiBase } = useWorkspaceSession();
  const zh = locale === "zh-TW";
  const [siteId, setSiteId] = useState("1");
  const [timeoutMs, setTimeoutMs] = useState("5000");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OpenOcdControlPlaneResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(): Promise<void> {
    if (running) return;
    const site = Number.parseInt(siteId, 10);
    const timeout = Number.parseInt(timeoutMs, 10);
    if (!Number.isInteger(site) || site < 1) {
      setError(zh ? "Site ID 必須是從 1 開始的正整數。" : "Site ID must be a positive one-based integer.");
      return;
    }
    if (!Number.isInteger(timeout) || timeout < 100 || timeout > 30000) {
      setError(zh ? "Timeout 必須介於 100 到 30000 ms。" : "Timeout must be between 100 and 30000 ms.");
      return;
    }

    setRunning(true);
    setResult(null);
    setError(null);
    try {
      setResult(await executeOpenOcdControlPlane(apiBase, { site_id: site, timeout_ms: timeout }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  }

  return (
    <DiagnosticsTestPage
      eyebrow="EMODE / DIAGNOSTICS / OPENOCD CONTROL PLANE"
      title={zh ? "OpenOCD Control Plane Test" : "OpenOCD Control Plane Test"}
      description={zh
        ? "驗證 Control Console → Manager → PPU Gateway → PS → OpenOCD Worker → Tcl RPC。只測控制面，不接觸 SWD/JTAG、PL 或 IC。"
        : "Validates Control Console → Manager → PPU Gateway → PS → OpenOCD Worker → Tcl RPC. Control plane only; no SWD/JTAG, PL or IC access."}
    >
      <DiagnosticsTestNotice>
        <strong>{zh ? "安全邊界：" : "Safety boundary:"}</strong>{" "}
        {zh
          ? "Browser 無法提交 Tcl command；PPU 固定只執行安全的 version probe。hardware_runtime_ready 永遠保持 false。"
          : "The Browser cannot submit Tcl commands. The PPU runs only the fixed safe version probe. hardware_runtime_ready remains false."}
      </DiagnosticsTestNotice>

      <DiagnosticsTestCard
        title={zh ? "Test Configuration" : "Test Configuration"}
        description={zh ? "Site 只決定 worker identity；本測試使用 dummy adapter，不會操作目標硬體。" : "Site selects worker identity only. The diagnostic uses the dummy adapter and never accesses target hardware."}
      >
        <div className="openocdControlPlaneForm">
          <label className="operatorField">
            <span>Site ID</span>
            <input
              type="number"
              min={1}
              step={1}
              value={siteId}
              disabled={running}
              onChange={event => setSiteId(event.target.value)}
            />
          </label>
          <label className="operatorField">
            <span>Timeout (ms)</span>
            <input
              type="number"
              min={100}
              max={30000}
              step={100}
              value={timeoutMs}
              disabled={running}
              onChange={event => setTimeoutMs(event.target.value)}
            />
          </label>
          <button className="operatorButton" type="button" disabled={running} onClick={() => void run()}>
            {running ? (zh ? "執行中…" : "Running…") : (zh ? "Start Test" : "Start Test")}
          </button>
        </div>
        {error && <p className="openocdControlPlaneError" role="alert">{error}</p>}
      </DiagnosticsTestCard>

      <DiagnosticsTestCard title={zh ? "Control-Plane Evidence" : "Control-Plane Evidence"}>
        {!result ? (
          <p className="openocdControlPlaneEmpty">{zh ? "尚未執行測試。" : "No test has been executed."}</p>
        ) : (
          <>
            <div className="openocdControlPlaneHeadline" data-pass={result.result === "PASS"}>
              <span>OpenOCD Control Plane</span>
              <strong>{result.result}</strong>
            </div>
            <div className="openocdControlPlaneGrid">
              <article><small>Site</small><strong>{result.site_id}</strong></article>
              <article><small>OpenOCD</small><strong>{result.openocd_version}</strong></article>
              <article><small>Runtime</small><strong>{result.runtime_id}</strong></article>
              <article><small>Process</small><strong>{result.probe_process_state.toUpperCase()} → {result.process_state.toUpperCase()}</strong></article>
              <article><small>Tcl RPC</small><strong>{result.tcl_rpc_state.toUpperCase()}</strong></article>
              <article><small>RPC Scope</small><strong>{result.rpc_scope}</strong></article>
              <article><small>Architecture</small><strong>{result.architecture}</strong></article>
              <article><small>Worker Generation</small><strong>{result.worker_generation}</strong></article>
              <article><small>PPU Latency</small><strong>{result.latency_ms.toFixed(3)} ms</strong></article>
              <article><small>Manager RTT</small><strong>{result.manager.manager_rtt_ms.toFixed(3)} ms</strong></article>
              <article><small>Capability</small><strong>{result.execution_capability}</strong></article>
              <article data-warning="true"><small>Hardware Runtime Ready</small><strong>NO</strong></article>
            </div>
          </>
        )}
      </DiagnosticsTestCard>
    </DiagnosticsTestPage>
  );
}
