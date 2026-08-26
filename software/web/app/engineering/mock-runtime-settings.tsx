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

const guideCopy = {
  "zh-TW": {
    eyebrow: "OPERATOR GUIDE",
    title: "Mock 設定說明",
    intro: "Mock Runtime 用來驗證 Plasma 軟體流程，不需要實體 PPU/IC。設定由 Gateway server 保存，PMode 與 EMode Programming 共用。",
    items: [
      ["Enabled", "開啟後使用 Profile timing / error injection；關閉時不套用這組注入設定。"],
      ["Default Image Size", "Mock Synthetic Image 的預設大小，範圍 64–4096 KiB，以 64 KiB 為單位。"],
      ["Seed Mode", "Auto 由 server 解析 execution seed；Fixed 適合記錄並重現受控測試條件。Batch START 後 seed/profile snapshot 不再被新設定改變。"],
      ["Error Rate", "E/P/V/R 每次 operation attempt 的軟體失敗機率，解析度 0.1%；它不是 Gateway/network 斷線率。"],
      ["Base Time / Throughput / Jitter", "共同決定每個 operation 的模擬執行時間；Jitter 是額外的 ± 時間變動。"],
      ["Applied Configuration", "這張表才是 server 已接受的 source of truth；未 Apply 的欄位只是 draft。"],
    ],
    testTitle: "測試方法",
    testIntro: "可用下面三組測試快速驗證基本流程、失敗/retry 與 timing 行為。",
    tests: [
      ["基本 PASS 測試", "Enabled = ON、Fixed Seed = 424242、E/P/V/R Error Rate = 0.0%、Jitter = 0。Apply 後在 PMode/EMode 執行 Batch，預期選定操作全部成功。"],
      ["Failure / Retry 測試", "把 Program Error Rate 設為 100.0%，Apply 後執行包含 Program 的 Batch；若 Site Retry Limit = 2，Program 最多會有 3 次 attempt，最後該 Site 應成為 FAULTED。"],
      ["Timing 測試", "設定明顯的 Base Time、固定 Image Size 並將 Jitter = 0；執行後比較 operation elapsed time。實際時間可包含排程與 UI/REST overhead，不要求毫秒級完全相等。"],
    ],
    caution: "Mock PASS 只能證明軟體 workflow / contract；不能宣稱 Z2、FPGA、socket、OpenOCD 或真實 IC programming 已驗證。",
  },
  "en-US": {
    eyebrow: "OPERATOR GUIDE",
    title: "Mock Settings Guide",
    intro: "Mock Runtime exercises Plasma software flows without a physical PPU or IC. The Gateway server persists one configuration shared by PMode and EMode Programming.",
    items: [
      ["Enabled", "Enables Profile timing and error injection. When disabled, this injection profile is not applied."],
      ["Default Image Size", "Default Mock Synthetic Image size, from 64 to 4096 KiB in 64 KiB steps."],
      ["Seed Mode", "Auto lets the server resolve an execution seed; Fixed is useful for recorded controlled test conditions. A started Batch keeps its frozen seed/profile snapshot."],
      ["Error Rate", "Software failure probability for each E/P/V/R operation attempt at 0.1% resolution. It is not a Gateway or network disconnect rate."],
      ["Base Time / Throughput / Jitter", "Together they determine simulated operation duration; Jitter adds a ± timing variation."],
      ["Applied Configuration", "This table is the server-accepted source of truth. Unapplied form values are only a draft."],
    ],
    testTitle: "Test Method",
    testIntro: "Use these three checks to validate basic flow, failure/retry behavior, and timing.",
    tests: [
      ["Basic PASS", "Set Enabled ON, Fixed Seed 424242, all E/P/V/R Error Rates to 0.0%, and Jitter to 0. Apply, then run a PMode/EMode Batch; all selected operations should succeed."],
      ["Failure / Retry", "Set Program Error Rate to 100.0%, apply, then run a Batch containing Program. With Site Retry Limit = 2, Program can have up to three attempts before the Site becomes FAULTED."],
      ["Timing", "Choose an obvious Base Time, fixed Image Size, and Jitter = 0. Run an operation and compare elapsed time. Scheduler and UI/REST overhead mean millisecond-perfect equality is not required."],
    ],
    caution: "A Mock PASS validates only the software workflow and contract. It does not validate Z2, FPGA, sockets, OpenOCD, or real IC programming.",
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
  const guide = guideCopy[locale];
  const { apiBase } = useWorkspaceSession();
  const [applied, setApplied] = useState<MockRuntimeSettings | null>(null);
  const [draft, setDraft] = useState<MockRuntimeSettings | null>(null);
  const [loadedApiBase, setLoadedApiBase] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMockRuntimeSettings(apiBase)
      .then(settings => {
        if (cancelled) return;
        setApplied(settings);
        setDraft(cloneSettings(settings));
        setError(null);
        setNotice(null);
        setLoadedApiBase(apiBase);
      })
      .catch(reason => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : text.unavailable);
        setLoadedApiBase(apiBase);
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

  if (loadedApiBase !== apiBase) {
    return <div className="mockRuntimeLoading" role="status">{text.loading}</div>;
  }
  if (!draft || !applied || error && applied === null) {
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

      <section className="mockRuntimeGuide" aria-label="Mock Settings Guide">
        <header>
          <small>{guide.eyebrow}</small>
          <h3>{guide.title}</h3>
          <p>{guide.intro}</p>
        </header>
        <div className="mockRuntimeGuideGrid">
          <article>
            <dl>
              {guide.items.map(([term, description]) => (
                <div key={term}><dt>{term}</dt><dd>{description}</dd></div>
              ))}
            </dl>
          </article>
          <article>
            <h4>{guide.testTitle}</h4>
            <p>{guide.testIntro}</p>
            <ol>
              {guide.tests.map(([name, description]) => (
                <li key={name}><b>{name}</b><span>{description}</span></li>
              ))}
            </ol>
          </article>
        </div>
        <p className="mockRuntimeCaution">{guide.caution}</p>
      </section>
    </div>
  );
}
