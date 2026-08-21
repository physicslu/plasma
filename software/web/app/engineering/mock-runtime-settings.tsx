"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  getMockRuntimeSettings,
  updateMockRuntimeSettings,
  type MockOperationProfile,
  type MockRuntimeSettings,
} from "../mock-runtime-api";
import { useWorkspaceSession } from "../workspace-session";
import "./mock-runtime-settings.css";

const operationOrder = ["erase", "program", "verify", "read"] as const;
type MockOperation = (typeof operationOrder)[number];

const copy = {
  "zh-TW": {
    eyebrow: "MOCK RUNTIME CONFIGURATION",
    title: "Mock 設定",
    subtitle: "同一份設定供 Production 與 Engineering Programming 使用；Batch 啟動時凍結 Profile revision 與 Seed。",
    loading: "正在讀取 Mock Runtime 設定…",
    unavailable: "Mock Runtime 設定無法使用。請確認 Gateway 已啟用 Engineering Mock Provider。",
    profileEnabled: "啟用 Profile timing / error injection",
    imageSize: "Default Image Size (KiB)",
    seedMode: "Seed Mode",
    fixedSeed: "Fixed Seed",
    auto: "Auto",
    fixed: "Fixed",
    operation: "Operation",
    errorRate: "Error Rate (%)",
    baseTime: "Base Time (ms)",
    throughput: "Throughput (KiB/s)",
    jitter: "Jitter (±ms)",
    apply: "Apply Settings",
    reset: "Reset Draft",
    applying: "Applying…",
    validation: "設定值無效：Error Rate 需 0–100% 且解析度 0.1%；Image Size 64–4096 KiB 且以 64 KiB 為單位。",
    applied: "Applied Configuration",
    revision: "Revision",
    profileId: "Profile ID",
    seed: "Seed",
    saved: "設定已套用。新的 Job/Batch 使用新 revision；已在執行中的 Batch 保持原快照。",
    probabilityHint: "0.1% = 1 per-mille。Retry 每次使用不同 deterministic attempt seed。",
    persistenceHint: "設定由 Gateway server 保存；Batch snapshot 會記錄實際 Profile revision 與 resolved seed。",
  },
  "en-US": {
    eyebrow: "MOCK RUNTIME CONFIGURATION",
    title: "Mock Settings",
    subtitle: "One configuration drives Production and Engineering Programming; each Batch freezes its Profile revision and Seed.",
    loading: "Loading Mock Runtime settings…",
    unavailable: "Mock Runtime settings are unavailable. Enable the Engineering Mock Provider on the Gateway.",
    profileEnabled: "Enable Profile timing / error injection",
    imageSize: "Default Image Size (KiB)",
    seedMode: "Seed Mode",
    fixedSeed: "Fixed Seed",
    auto: "Auto",
    fixed: "Fixed",
    operation: "Operation",
    errorRate: "Error Rate (%)",
    baseTime: "Base Time (ms)",
    throughput: "Throughput (KiB/s)",
    jitter: "Jitter (±ms)",
    apply: "Apply Settings",
    reset: "Reset Draft",
    applying: "Applying…",
    validation: "Invalid values: Error Rate must be 0–100% at 0.1% resolution; Image Size must be 64–4096 KiB in 64 KiB steps.",
    applied: "Applied Configuration",
    revision: "Revision",
    profileId: "Profile ID",
    seed: "Seed",
    saved: "Settings applied. New Jobs/Batches use the new revision; running Batches retain their frozen snapshot.",
    probabilityHint: "0.1% = 1 per-mille. Every Retry uses a distinct deterministic attempt seed.",
    persistenceHint: "Settings are persisted by the Gateway; Batch snapshots record the effective Profile revision and resolved seed.",
  },
} as const;

function cloneSettings(settings: MockRuntimeSettings): MockRuntimeSettings {
  return {
    ...settings,
    seed: { ...settings.seed },
    operations: Object.fromEntries(
      operationOrder.map(operation => [operation, { ...settings.operations[operation] }]),
    ) as MockRuntimeSettings["operations"],
  };
}

function isInteger(value: number): boolean {
  return Number.isFinite(value) && Number.isInteger(value);
}

function validate(settings: MockRuntimeSettings): boolean {
  const imageKiB = settings.default_image_size_bytes / 1024;
  if (!isInteger(imageKiB) || imageKiB < 64 || imageKiB > 4096 || imageKiB % 64 !== 0) return false;
  if (settings.seed.mode === "fixed") {
    const seed = settings.seed.fixed_seed;
    if (seed === null || !Number.isSafeInteger(seed) || seed < 0) return false;
  }
  return operationOrder.every(operation => {
    const profile = settings.operations[operation];
    return isInteger(profile.error_rate_per_mille)
      && profile.error_rate_per_mille >= 0
      && profile.error_rate_per_mille <= 1000
      && isInteger(profile.base_time_ms)
      && profile.base_time_ms >= 0
      && isInteger(profile.throughput_bytes_per_second)
      && profile.throughput_bytes_per_second > 0
      && isInteger(profile.jitter_ms)
      && profile.jitter_ms >= 0;
  });
}

function operationLabel(operation: MockOperation): string {
  return operation[0].toUpperCase() + operation.slice(1);
}

export default function MockRuntimeSettingsPanel() {
  const { locale } = useI18n();
  const text = copy[locale];
  const { apiBase } = useWorkspaceSession();
  const [applied, setApplied] = useState<MockRuntimeSettings | null>(null);
  const [draft, setDraft] = useState<MockRuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getMockRuntimeSettings(apiBase)
      .then(settings => {
        if (cancelled) return;
        setApplied(settings);
        setDraft(cloneSettings(settings));
      })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : text.unavailable);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [apiBase, text.unavailable]);

  const valid = useMemo(() => Boolean(draft && validate(draft)), [draft]);

  function updateOperation(operation: MockOperation, patch: Partial<MockOperationProfile>) {
    setDraft(current => current ? {
      ...current,
      operations: {
        ...current.operations,
        [operation]: { ...current.operations[operation], ...patch },
      },
    } : current);
  }

  async function applySettings() {
    if (!draft || !valid || saving) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await updateMockRuntimeSettings(apiBase, draft);
      setApplied(next);
      setDraft(cloneSettings(next));
      setNotice(text.saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : text.unavailable);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="mockRuntimeLoading" role="status">{text.loading}</div>;
  }
  if (!draft || !applied) {
    return <div className="mockRuntimeError" role="alert">{error ?? text.unavailable}</div>;
  }

  return (
    <div className="mockRuntimePanel">
      <header className="mockRuntimeHeader">
        <div>
          <small>{text.eyebrow}</small>
          <h2>{text.title}</h2>
          <p>{text.subtitle}</p>
        </div>
        <div className="mockRevisionBadge">REV {applied.revision}</div>
      </header>

      <section className="mockRuntimeControls" aria-label="Mock runtime controls">
        <label className="mockRuntimeToggle">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={event => setDraft({ ...draft, enabled: event.target.checked })}
          />
          <span>{text.profileEnabled}</span>
        </label>

        <div className="mockRuntimeMetaGrid">
          <label>
            <span>{text.imageSize}</span>
            <input
              type="number"
              min={64}
              max={4096}
              step={64}
              value={draft.default_image_size_bytes / 1024}
              onChange={event => setDraft({
                ...draft,
                default_image_size_bytes: Number(event.target.value) * 1024,
              })}
            />
          </label>
          <label>
            <span>{text.seedMode}</span>
            <select
              value={draft.seed.mode}
              onChange={event => {
                const mode = event.target.value as "auto" | "fixed";
                setDraft({
                  ...draft,
                  seed: {
                    mode,
                    fixed_seed: mode === "fixed" ? (draft.seed.fixed_seed ?? 1) : null,
                  },
                });
              }}
            >
              <option value="auto">{text.auto}</option>
              <option value="fixed">{text.fixed}</option>
            </select>
          </label>
          <label>
            <span>{text.fixedSeed}</span>
            <input
              type="number"
              min={0}
              step={1}
              disabled={draft.seed.mode !== "fixed"}
              value={draft.seed.fixed_seed ?? ""}
              onChange={event => setDraft({
                ...draft,
                seed: { ...draft.seed, fixed_seed: Number(event.target.value) },
              })}
            />
          </label>
        </div>

        <div className="mockOperationTableWrap">
          <table className="mockOperationTable">
            <thead>
              <tr>
                <th>{text.operation}</th>
                <th>{text.errorRate}</th>
                <th>{text.baseTime}</th>
                <th>{text.throughput}</th>
                <th>{text.jitter}</th>
              </tr>
            </thead>
            <tbody>
              {operationOrder.map(operation => {
                const profile = draft.operations[operation];
                return (
                  <tr key={operation}>
                    <th scope="row">{operationLabel(operation)}</th>
                    <td>
                      <input
                        aria-label={`${operationLabel(operation)} error rate percent`}
                        type="number"
                        min={0}
                        max={100}
                        step={0.1}
                        value={profile.error_rate_per_mille / 10}
                        onChange={event => updateOperation(operation, {
                          error_rate_per_mille: Math.round(Number(event.target.value) * 10),
                        })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`${operationLabel(operation)} base time milliseconds`}
                        type="number"
                        min={0}
                        step={1}
                        value={profile.base_time_ms}
                        onChange={event => updateOperation(operation, { base_time_ms: Number(event.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`${operationLabel(operation)} throughput KiB per second`}
                        type="number"
                        min={1}
                        step={1}
                        value={profile.throughput_bytes_per_second / 1024}
                        onChange={event => updateOperation(operation, {
                          throughput_bytes_per_second: Math.round(Number(event.target.value) * 1024),
                        })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`${operationLabel(operation)} jitter milliseconds`}
                        type="number"
                        min={0}
                        step={1}
                        value={profile.jitter_ms}
                        onChange={event => updateOperation(operation, { jitter_ms: Number(event.target.value) })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="mockRuntimeHint">{text.probabilityHint}</p>
        {!valid && <p className="mockRuntimeValidation" role="alert">{text.validation}</p>}
        {error && <p className="mockRuntimeValidation" role="alert">{error}</p>}
        {notice && <p className="mockRuntimeNotice" role="status">{notice}</p>}

        <div className="mockRuntimeActions">
          <button
            type="button"
            className="mockApplyButton"
            disabled={!valid || saving}
            onClick={applySettings}
          >
            {saving ? text.applying : text.apply}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              setDraft(cloneSettings(applied));
              setError(null);
              setNotice(null);
            }}
          >
            {text.reset}
          </button>
        </div>
      </section>

      <section className="mockAppliedSummary" aria-label={text.applied}>
        <div className="mockAppliedHeader">
          <div>
            <small>SERVER-AUTHORITATIVE SNAPSHOT SOURCE</small>
            <h3>{text.applied}</h3>
          </div>
          <p>{text.persistenceHint}</p>
        </div>
        <dl className="mockAppliedMeta">
          <div><dt>{text.profileId}</dt><dd>{applied.profile_id}</dd></div>
          <div><dt>{text.revision}</dt><dd>{applied.revision}</dd></div>
          <div><dt>{text.seed}</dt><dd>{applied.seed.mode === "fixed" ? `fixed · ${applied.seed.fixed_seed}` : "auto"}</dd></div>
          <div><dt>{text.imageSize}</dt><dd>{applied.default_image_size_bytes / 1024} KiB</dd></div>
        </dl>
        <table className="mockAppliedTable">
          <thead>
            <tr>
              <th>{text.operation}</th>
              <th>{text.errorRate}</th>
              <th>{text.baseTime}</th>
              <th>{text.throughput}</th>
              <th>{text.jitter}</th>
            </tr>
          </thead>
          <tbody>
            {operationOrder.map(operation => {
              const profile = applied.operations[operation];
              return (
                <tr key={operation}>
                  <th scope="row">{operationLabel(operation)}</th>
                  <td>{(profile.error_rate_per_mille / 10).toFixed(1)}%</td>
                  <td>{profile.base_time_ms} ms</td>
                  <td>{Math.round(profile.throughput_bytes_per_second / 1024)} KiB/s</td>
                  <td>±{profile.jitter_ms} ms</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
