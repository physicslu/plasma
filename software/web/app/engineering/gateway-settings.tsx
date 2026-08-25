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

export default function GatewaySettingsPanel() {
  const { locale } = useI18n();
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
    </section>
  );
}
