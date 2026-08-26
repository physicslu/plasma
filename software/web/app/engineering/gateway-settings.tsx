"use client";

import { useEffect, useState } from "react";
import {
  getGatewaySettings,
  updateGatewaySettings,
  type GatewaySettings,
} from "../gateway-settings-api";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import "./gateway-settings.css";

const guideCopy = {
  "zh-TW": {
    eyebrow: "OPERATOR GUIDE",
    overviewTitle: "Gateway 設定說明",
    overviewBody: "這組設定控制 Plasma Web REST Gateway 與 PPU 之間的共用通訊政策，PMode 與 EMode 使用同一份 server-owned 設定。",
    timeoutTitle: "Request Timeout",
    timeoutBody: "單次 PPU request 最長等待時間。範圍 1–120 秒，預設 10 秒。",
    retryTitle: "Retry Count",
    retryBody: "暫時性通訊錯誤的追加重試次數。範圍 0–10 次，預設 3 次；等待間隔為 1、2、4 秒，之後維持 4 秒。",
    freezeTitle: "Batch Policy Freeze",
    freezeBody: "Batch START 時會凍結當下的 Gateway policy revision；之後修改只影響下一個 Batch。",
    safetyTitle: "避免重複 Job",
    safetyBody: "Job submission 結果不確定時不會直接重送；取得 Job ID 後的 status observation 才使用通訊 retry。",
    testTitle: "測試方法",
    testIntro: "建議先驗證設定保存，再於受控測試環境驗證 timeout / retry 與單一 PPU 隔離。",
    testSteps: [
      "先設定 Request Timeout = 10 sec、Retry Count = 3，按 Apply Settings，確認 REV 增加。",
      "重新整理頁面，確認 10 sec / 3 retries 仍保留，證明設定由 Gateway server 保存。",
      "在測試環境讓單一 PPU/provider 的 status request 延遲超過 timeout，或暫時中斷該 PPU；使用至少兩個 PPU 啟動 Batch。",
      "確認通訊 retry 依 1、2、4 秒 backoff 執行；retry 用盡後只隔離失敗 PPU，健康 PPU 繼續執行。",
      "檢查 Live Site Status、Batch error 與 Engineering Job Log；通訊基礎設施異常應呈現 ERROR/STOPPED，而不是冒充 IC FAIL。",
    ],
    caution: "注意：Mock 的 E/P/V/R Error Rate 是操作失敗注入，不是 Gateway 斷線模擬，不能取代上述通訊 fault test。",
  },
  "en-US": {
    eyebrow: "OPERATOR GUIDE",
    overviewTitle: "Gateway Settings Guide",
    overviewBody: "These settings control the shared server-owned communication policy between the Plasma Web REST Gateway and PPUs. PMode and EMode use the same policy.",
    timeoutTitle: "Request Timeout",
    timeoutBody: "Maximum wait for one PPU request. Range: 1–120 seconds. Default: 10 seconds.",
    retryTitle: "Retry Count",
    retryBody: "Additional retries for transient communication errors. Range: 0–10. Default: 3. Backoff is 1, 2, then 4 seconds and remains at 4 seconds afterward.",
    freezeTitle: "Batch Policy Freeze",
    freezeBody: "A Batch freezes the current Gateway policy revision at START. Later edits apply only to the next Batch.",
    safetyTitle: "Avoid duplicate Jobs",
    safetyBody: "An uncertain Job submission is not blindly resent. Communication retry is used for status observation after a Job ID is known.",
    testTitle: "Test Method",
    testIntro: "First verify persistence, then validate timeout, retry, and single-PPU isolation in a controlled test environment.",
    testSteps: [
      "Set Request Timeout to 10 sec and Retry Count to 3, apply the settings, and confirm REV increments.",
      "Reload the page and confirm 10 sec / 3 retries remain, proving the Gateway server persisted the settings.",
      "In a test environment, delay one PPU/provider status request beyond the timeout or temporarily disconnect that PPU; start a Batch spanning at least two PPUs.",
      "Confirm retry follows the 1, 2, 4 second backoff; after exhaustion, only the failed PPU is isolated while healthy PPUs continue.",
      "Inspect Live Site Status, the Batch error, and Engineering Job Log. Infrastructure communication failures should be ERROR/STOPPED rather than IC FAIL.",
    ],
    caution: "Note: Mock E/P/V/R Error Rate injects operation failures, not Gateway disconnects, so it cannot replace this communication fault test.",
  },
} as const;

export default function GatewaySettingsPanel() {
  const { locale } = useI18n();
  const guide = guideCopy[locale];
  const { apiBase, hydrated } = useWorkspaceSession();
  const [applied, setApplied] = useState<GatewaySettings | null>(null);
  const [timeoutSeconds, setTimeoutSeconds] = useState("10");
  const [retryCount, setRetryCount] = useState("3");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;
    void getGatewaySettings(apiBase)
      .then(settings => {
        if (cancelled) return;
        setApplied(settings);
        setTimeoutSeconds(String(settings.ppu_request_timeout_ms / 1000));
        setRetryCount(String(settings.ppu_retry_count));
        setError(null);
      })
      .catch(loadError => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Gateway settings unavailable");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [apiBase, hydrated]);

  const parsedTimeout = Number(timeoutSeconds);
  const parsedRetries = Number(retryCount);
  const valid = Number.isInteger(parsedTimeout) && parsedTimeout >= 1 && parsedTimeout <= 120
    && Number.isInteger(parsedRetries) && parsedRetries >= 0 && parsedRetries <= 10;
  const changed = Boolean(applied && (
    parsedTimeout * 1000 !== applied.ppu_request_timeout_ms
    || parsedRetries !== applied.ppu_retry_count
  ));

  async function apply() {
    if (!valid || !changed || saving) return;
    setSaving(true);
    setSaved(false);
    try {
      const next = await updateGatewaySettings(apiBase, {
        ppu_request_timeout_ms: parsedTimeout * 1000,
        ppu_retry_count: parsedRetries,
      });
      setApplied(next);
      setTimeoutSeconds(String(next.ppu_request_timeout_ms / 1000));
      setRetryCount(String(next.ppu_retry_count));
      setError(null);
      setSaved(true);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Gateway settings update failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="engineeringGatewaySettings" aria-label="Engineering Settings">
      <header className="gatewaySettingsHeading">
        <div><small>ENGINEERING MODE</small><h1>Settings</h1></div>
        {applied && <span>REV {applied.revision}</span>}
      </header>

      <nav className="gatewaySettingsTabs" aria-label="Engineering settings categories">
        <button type="button" aria-current="page">Gateway</button>
      </nav>

      <section className="gatewaySettingsCard" aria-label="Gateway Communication Settings">
        <header>
          <h2>Gateway</h2>
          <p>{locale === "zh-TW"
            ? "設定 Plasma Web REST Gateway 與 PPU 的通訊逾時及重試規則；PMode 與 EMode 共用。"
            : "Configure shared Plasma Web REST Gateway to PPU communication timeout and retry policy."}</p>
        </header>

        <div className="gatewaySettingsFields">
          <label>
            <span>Request Timeout</span>
            <div><input aria-label="PPU Request Timeout seconds" type="number" min="1" max="120" value={timeoutSeconds} disabled={loading || saving} onChange={event => { setSaved(false); setTimeoutSeconds(event.target.value); }} /><b>sec</b></div>
            <small>1–120 seconds</small>
          </label>
          <label>
            <span>Retry Count</span>
            <div><input aria-label="PPU Retry Count" type="number" min="0" max="10" value={retryCount} disabled={loading || saving} onChange={event => { setSaved(false); setRetryCount(event.target.value); }} /><b>times</b></div>
            <small>0–10 retries</small>
          </label>
        </div>

        <p className="gatewaySettingsHint">{locale === "zh-TW"
          ? "重試間隔依序為 1、2、4 秒，後續維持 4 秒。執行中的 Batch 保留開始時的設定；修改只影響下一個 Batch。"
          : "Retry backoff is 1, 2, then 4 seconds. Running Batches retain their frozen settings; changes apply to the next Batch."}</p>

        {error && <p className="gatewaySettingsError" role="alert">{error}</p>}
        {saved && <p className="gatewaySettingsSaved" role="status">{locale === "zh-TW" ? "Gateway 設定已儲存。" : "Gateway settings saved."}</p>}

        <div className="gatewaySettingsActions">
          <button type="button" disabled={!valid || !changed || loading || saving} onClick={() => void apply()}>
            {saving ? "Saving..." : "Apply Settings"}
          </button>
        </div>
      </section>

      <section className="gatewaySettingsGuide" aria-label="Gateway Settings Guide">
        <header>
          <small>{guide.eyebrow}</small>
          <h2>{guide.overviewTitle}</h2>
          <p>{guide.overviewBody}</p>
        </header>

        <div className="gatewaySettingsGuideGrid">
          <article>
            <dl>
              <div><dt>{guide.timeoutTitle}</dt><dd>{guide.timeoutBody}</dd></div>
              <div><dt>{guide.retryTitle}</dt><dd>{guide.retryBody}</dd></div>
              <div><dt>{guide.freezeTitle}</dt><dd>{guide.freezeBody}</dd></div>
              <div><dt>{guide.safetyTitle}</dt><dd>{guide.safetyBody}</dd></div>
            </dl>
          </article>
          <article>
            <h3>{guide.testTitle}</h3>
            <p>{guide.testIntro}</p>
            <ol>
              {guide.testSteps.map(step => <li key={step}>{step}</li>)}
            </ol>
          </article>
        </div>

        <p className="gatewaySettingsCaution">{guide.caution}</p>
      </section>
    </section>
  );
}
