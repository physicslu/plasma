"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type Locale = "zh-TW" | "en-US";
type Catalog = Record<string, string>;

const catalogs: Record<Locale, Catalog> = {
  "zh-TW": {
    "nav.entry": "入口",
    "mode.label": "產品模式", "mode.production": "量產模式", "mode.engineering": "工程模式",
    "locale.zh": "繁中", "locale.en": "EN",
    "production.title": "Factory Production Console",
    "production.subtitle": "工廠量產監控 · 所有 PPU × Site 同畫面",
    "production.readOnly": "目前多 PPU 控制路徑維持唯讀；跨 PPU 寫入需另行啟用受認證控制路徑。",
    "summary.ppuOnline": "PPU Online", "summary.sites": "Sites", "summary.running": "Running", "summary.pass": "PASS", "summary.fail": "FAIL", "summary.offline": "Offline",
    "selection.selectedSites": "已選 Sites", "selection.clear": "清除全部", "selection.selectAll": "全選", "selection.deselectAll": "全部取消",
    "selection.operations": "操作", "selection.execute": "執行批次", "selection.cancel": "取消批次", "selection.writeLocked": "跨 PPU 寫入控制尚未啟用",
    "status.ready": "READY", "status.running": "RUNNING", "status.pass": "PASS", "status.fail": "FAIL", "status.error": "ERROR", "status.disabled": "DISABLED", "status.offline": "OFFLINE", "status.stale": "STALE",
    "site.execution": "Execution", "site.lastResult": "Last Result", "site.operation": "Operation", "site.progress": "Progress", "site.interface": "Interface", "site.target": "Target", "site.clearResult": "清除結果", "site.detail": "Site Detail", "site.none": "NONE",
    "ppu.transport": "Transport", "ppu.gateway": "Gateway", "ppu.sites": "Sites",
    "log.title": "Factory Log Console", "log.all": "全部 Log", "log.errors": "Errors Only", "log.autoScroll": "Auto-scroll", "log.full": "全螢幕 Log", "log.closeFull": "返回主畫面", "log.clear": "清除畫面 Log",
    "log.time": "時間", "log.ppu": "PPU", "log.site": "SITE", "log.level": "級別", "log.operation": "操作", "log.message": "訊息", "log.empty": "目前沒有符合條件的 Log。",
    "log.observationNote": "本版顯示 Manager 多 PPU observation 與 PPU latest-job 摘要；完整逐階段 programming event log transport 將另行擴充。",
    "log.event.fleetConnected": "多 PPU observation connected", "log.event.ppuChanged": "PPU 狀態變更", "log.event.siteChanged": "Site 狀態變更", "log.event.jobObserved": "Job 狀態更新", "log.event.siteResultCleared": "Latched result 已由操作員清除",
    "fleet.connecting": "Connecting", "fleet.online": "Online", "fleet.disabled": "Disabled", "fleet.unavailable": "Unavailable", "fleet.disabledTitle": "量產模式的多 PPU 觀測未在此 Host 啟用", "fleet.unavailableTitle": "量產模式資料暫時無法取得", "fleet.managerIndependent": "Manager 的多 PPU 聚合不在本機 Site execution path；單機 PPU 仍可獨立運作。",
    "engineering.title": "Engineering Mode", "engineering.subtitle": "工程工作台骨架；預留 IC、演算法、診斷與低階工具的擴充空間。", "engineering.overview": "Overview", "engineering.ppuSites": "PPU / Sites", "engineering.programming": "Programming", "engineering.diagnostics": "Diagnostics", "engineering.logs": "Logs", "engineering.tools": "Tools", "engineering.settings": "Settings", "engineering.placeholder": "此區先建立穩定的資訊架構與 extension slots，詳細工程功能將分階段加入。",
    "operation.erase": "擦除", "operation.program": "燒錄", "operation.verify": "驗證", "operation.read": "讀取",
  },
  "en-US": {
    "nav.entry": "Demo",
    "mode.label": "Product mode", "mode.production": "Production Mode", "mode.engineering": "Engineering Mode",
    "locale.zh": "繁中", "locale.en": "EN",
    "production.title": "Factory Production Console",
    "production.subtitle": "Factory production monitoring · all PPUs × Sites on one screen",
    "production.readOnly": "Multi-PPU control remains read-only. Cross-PPU writes require the separately approved authenticated control path.",
    "summary.ppuOnline": "PPU Online", "summary.sites": "Sites", "summary.running": "Running", "summary.pass": "PASS", "summary.fail": "FAIL", "summary.offline": "Offline",
    "selection.selectedSites": "Selected Sites", "selection.clear": "Clear All", "selection.selectAll": "Select All", "selection.deselectAll": "Deselect All", "selection.operations": "Operations", "selection.execute": "Execute Batch", "selection.cancel": "Cancel Batch", "selection.writeLocked": "Cross-PPU write control is not enabled",
    "status.ready": "READY", "status.running": "RUNNING", "status.pass": "PASS", "status.fail": "FAIL", "status.error": "ERROR", "status.disabled": "DISABLED", "status.offline": "OFFLINE", "status.stale": "STALE",
    "site.execution": "Execution", "site.lastResult": "Last Result", "site.operation": "Operation", "site.progress": "Progress", "site.interface": "Interface", "site.target": "Target", "site.clearResult": "Clear Result", "site.detail": "Site Detail", "site.none": "NONE",
    "ppu.transport": "Transport", "ppu.gateway": "Gateway", "ppu.sites": "Sites",
    "log.title": "Factory Log Console", "log.all": "All Logs", "log.errors": "Errors Only", "log.autoScroll": "Auto-scroll", "log.full": "Full Log View", "log.closeFull": "Back to Console", "log.clear": "Clear View",
    "log.time": "Time", "log.ppu": "PPU", "log.site": "SITE", "log.level": "Level", "log.operation": "Operation", "log.message": "Message", "log.empty": "No log entries match the current filter.",
    "log.observationNote": "This version displays Manager multi-PPU observations and safe PPU latest-job summaries. Full per-stage programming event-log transport will be added separately.",
    "log.event.fleetConnected": "Multi-PPU observation connected", "log.event.ppuChanged": "PPU state changed", "log.event.siteChanged": "Site state changed", "log.event.jobObserved": "Job state updated", "log.event.siteResultCleared": "Latched result cleared by operator",
    "fleet.connecting": "Connecting", "fleet.online": "Online", "fleet.disabled": "Disabled", "fleet.unavailable": "Unavailable", "fleet.disabledTitle": "Multi-PPU observation is not enabled for Production Mode on this host", "fleet.unavailableTitle": "Production Mode data is unavailable", "fleet.managerIndependent": "Manager multi-PPU aggregation is outside the local Site execution path; single-PPU operation remains independent.",
    "engineering.title": "Engineering Mode", "engineering.subtitle": "Engineering workspace foundation with room for IC, algorithm, diagnostics and low-level tools.", "engineering.overview": "Overview", "engineering.ppuSites": "PPU / Sites", "engineering.programming": "Programming", "engineering.diagnostics": "Diagnostics", "engineering.logs": "Logs", "engineering.tools": "Tools", "engineering.settings": "Settings", "engineering.placeholder": "This release establishes stable information architecture and extension slots. Detailed engineering capabilities will be added incrementally.",
    "operation.erase": "Erase", "operation.program": "Program", "operation.verify": "Verify", "operation.read": "Read",
  },
};

type I18nContextValue = { locale: Locale; setLocale: (locale: Locale) => void; t: (key: string) => string };
const I18nContext = createContext<I18nContextValue | null>(null);
const STORAGE_KEY = "plasma-locale";

function normalizeLocale(value: string | null): Locale {
  return value === "en-US" ? "en-US" : "zh-TW";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  // Keep the first client render identical to SSR, then restore the persisted
  // preference after hydration. User-triggered changes update React state
  // directly, so switching language never waits on storage/event propagation.
  const [locale, setLocaleState] = useState<Locale>("zh-TW");

  useEffect(() => {
    try { setLocaleState(normalizeLocale(window.localStorage.getItem(STORAGE_KEY))); } catch { /* storage is optional */ }

    const syncFromStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setLocaleState(normalizeLocale(event.newValue));
    };
    window.addEventListener("storage", syncFromStorage);
    return () => window.removeEventListener("storage", syncFromStorage);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* storage is optional */ }
  }, []);

  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const value = useMemo<I18nContextValue>(() => ({ locale, setLocale, t: (key: string) => catalogs[locale][key] ?? catalogs["en-US"][key] ?? key }), [locale, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
