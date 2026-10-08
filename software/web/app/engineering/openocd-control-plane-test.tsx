"use client";

import { useState } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import { DiagnosticsTestCard, DiagnosticsTestNotice, DiagnosticsTestPage } from "./diagnostics-test-page";
import { executeOpenOcdControlPlane, type OpenOcdControlPlaneResponse } from "./openocd-control-plane-api";
import "./diagnostics-test-page.css";
import "./diagnostics-evidence.css";
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
      title="OpenOCD Control Plane Test"
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
        title={zh ? "測試設定" : "Test Configuration"}
        description={zh
          ? "Site 只決定 worker identity；本測試使用 dummy adapter，不會操作目標硬體。"
          : "Site selects worker identity only. The diagnostic uses the dummy adapter and never accesses target hardware."}
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
            {running ? (zh ? "執行中…" : "Running…") : (zh ? "開始測試" : "Start Test")}
          </button>
        </div>
        {error && <p className="openocdControlPlaneError" role="alert">{error}</p>}
      </DiagnosticsTestCard>

      <DiagnosticsTestCard title={zh ? "控制面驗證結果" : "Control-Plane Evidence"}>
        {!result ? (
          <p className="openocdControlPlaneEmpty">{zh ? "尚未執行測試。" : "No test has been executed."}</p>
        ) : (
          <div className="diagnosticsEvidence">
            <div className="diagnosticsEvidenceHeadline" data-result={result.result}>
              <div>
                <small>{zh ? "控制面狀態" : "Control-plane status"}</small>
                <strong>OpenOCD Control Plane</strong>
                <span>{zh ? "控制面驗證通過，worker 流程正常。" : "Control-plane validation passed and the worker lifecycle completed normally."}</span>
              </div>
              <span className="diagnosticsEvidenceBadge" data-result={result.result}>{result.result}</span>
            </div>

            <div className="diagnosticsEvidenceSectionGrid">
              <section className="diagnosticsEvidenceSection" data-tone="identity">
                <header>
                  <small>{zh ? "ENVIRONMENT" : "ENVIRONMENT"}</small>
                  <h4>{zh ? "基本資訊" : "Runtime Identity"}</h4>
                  <p>{zh ? "本次測試使用的環境與版本。" : "Environment and versions used by this probe."}</p>
                </header>
                <dl>
                  <div><dt>Site ID</dt><dd>{result.site_id}</dd></div>
                  <div><dt>{zh ? "OpenOCD 版本" : "OpenOCD Version"}</dt><dd>{result.openocd_version}</dd></div>
                  <div><dt>Runtime ID</dt><dd className="diagnosticsEvidenceMono">{result.runtime_id}</dd></div>
                  <div><dt>{zh ? "架構 (Architecture)" : "Architecture"}</dt><dd>{result.architecture}</dd></div>
                </dl>
              </section>

              <section className="diagnosticsEvidenceSection" data-tone="execution">
                <header>
                  <small>{zh ? "CONTROL PATH" : "CONTROL PATH"}</small>
                  <h4>{zh ? "執行狀態" : "Execution / RPC"}</h4>
                  <p>{zh ? "OpenOCD worker 與 Tcl RPC 的實際執行結果。" : "Observed OpenOCD worker and Tcl RPC behavior."}</p>
                </header>
                <dl>
                  <div>
                    <dt>{zh ? "Worker 生命週期" : "Worker Lifecycle"}</dt>
                    <dd><span className="diagnosticsStatusBadge" data-tone="success">{zh ? "啟動 → 正常停止" : "Started → Stopped normally"}</span></dd>
                  </div>
                  <div>
                    <dt>Tcl RPC</dt>
                    <dd><span className="diagnosticsStatusBadge" data-tone="success">{result.tcl_rpc_state.toUpperCase()}</span></dd>
                  </div>
                  <div><dt>RPC Scope</dt><dd>{result.rpc_scope}</dd></div>
                </dl>
              </section>

              <section className="diagnosticsEvidenceSection" data-tone="performance">
                <header>
                  <small>{zh ? "PERFORMANCE" : "PERFORMANCE"}</small>
                  <h4>{zh ? "效能指標" : "Performance"}</h4>
                  <p>{zh ? "本次測試的延遲與 worker 世代資訊。" : "Latency and worker generation captured by this probe."}</p>
                </header>
                <dl>
                  <div><dt>Worker Generation</dt><dd>{result.worker_generation}</dd></div>
                  <div><dt>PPU Latency</dt><dd>{result.latency_ms.toFixed(3)} ms</dd></div>
                  <div><dt>Manager RTT</dt><dd>{result.manager.manager_rtt_ms.toFixed(3)} ms</dd></div>
                </dl>
              </section>
            </div>

            <section className="diagnosticsEvidenceBoundary">
              <header>
                <small>{zh ? "QUALIFICATION BOUNDARY" : "QUALIFICATION BOUNDARY"}</small>
                <h4>{zh ? "能力與測試範圍" : "Capability & Test Boundary"}</h4>
                <p>{zh
                  ? "這些限制是本測試刻意保留的安全邊界，不代表測試失敗。"
                  : "These limits are intentional safety boundaries for this diagnostic, not failed checks."}</p>
              </header>
              <div className="diagnosticsEvidenceBoundaryGrid">
                <div className="diagnosticsEvidenceBoundaryItem">
                  <span>Execution Capability</span>
                  <strong className="diagnosticsEvidenceCapability">{result.execution_capability}</strong>
                  <small>{zh ? "僅驗證 OpenOCD 控制面與 Tcl RPC。" : "OpenOCD control plane and Tcl RPC only."}</small>
                </div>
                <div className="diagnosticsEvidenceBoundaryItem">
                  <span>Hardware Runtime Ready</span>
                  <strong className="diagnosticsStatusBadge" data-tone="neutral">NOT ENABLED</strong>
                  <small>{zh ? "本測試預期為 false；尚未啟用實體硬體執行。" : "Expected false for this test; physical hardware execution remains disabled."}</small>
                </div>
                <div className="diagnosticsEvidenceBoundaryItem" data-span="full">
                  <span>{zh ? "不包含的功能（本測試不涉及）" : "Not claimed by this test"}</span>
                  <div className="diagnosticsEvidenceTags">
                    {result.not_claimed.map(item => <span key={item}>{item}</span>)}
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}
      </DiagnosticsTestCard>
    </DiagnosticsTestPage>
  );
}
