"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

export type Locale = "zh-TW" | "en-US";
type Catalog = Record<string, string>;

const catalogs: Record<Locale, Catalog> = {
  "zh-TW": {
    "nav.entry": "入口",
    "mode.label": "產品模式", "mode.production": "量產模式", "mode.engineering": "工程模式",
    "locale.zh": "繁中", "locale.en": "EN",
    "demo.eyebrow": "PLASMA 產品入口",
    "demo.title": "選擇產品模式",
    "demo.lead": "PMode（Production Mode／量產模式）用於正式燒錄與批次量產作業；EMode（Engineering Mode／工程模式）用於工程開發、驗證、診斷與設定。",
    "demo.production.title": "工廠量產控制台",
    "demo.production.description": "工廠操作介面：同畫面監控多台 PPU × Sites、PASS / FAIL、批次選取與 Factory Log。",
    "demo.production.open": "開啟量產模式 →",
    "demo.engineering.title": "工程工作台",
    "demo.engineering.description": "工程與維護工作台：PPU / Sites、Programming、Diagnostics、Logs、Tools 與後續低階功能。",
    "demo.engineering.open": "開啟工程模式 →",
    "demo.boundary.title": "架構邊界",
    "demo.boundary.description": "Manager 聚合失效不會停止本地 PPU 燒錄。",
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
    "engineeringProgramming.workspace": "Engineering Programming 工作台",
    "engineeringProgramming.title": "Single PPU Programming",
    "engineeringProgramming.subtitle": "Facility → PPU → Site；E/P/V/R 全部由 Python Engineering PPU Provider 執行。",
    "engineeringProgramming.gateway": "Plasma Web REST Gateway",
    "engineeringProgramming.connect": "連線",
    "engineeringProgramming.providerOffline": "PPU Provider 離線",
    "engineeringProgramming.serverSource": "SERVER SOURCE OF TRUTH",
    "engineeringProgramming.serverSourceNote": "前端不建立 Mock topology；所有 target identity 由 Python Provider 回報。",
    "engineeringProgramming.siteSelection": "Site 選擇",
    "engineeringProgramming.selected": "已選",
    "engineeringProgramming.imageAsset": "—",
    "engineeringProgramming.imageAssetHint": "Program / Verify 共用 · Max 16 MiB",
    "engineeringProgramming.browse": "選擇燒錄檔",
    "engineeringProgramming.batchOperations": "批次操作",
    "engineeringProgramming.noSites": "尚未選擇 Site",
    "engineeringProgramming.idle": "待命",
    "engineeringProgramming.running": "工作中",
    "engineeringProgramming.success": "成功",
    "engineeringProgramming.cancelled": "取消",
    "engineeringProgramming.failed": "失敗",
    "engineeringProgramming.execute": "執行",
    "engineeringProgramming.cancel": "取消",
    "engineeringProgramming.cancelling": "取消中",
    "engineeringProgramming.imageAssetTooLarge": "Programming Image Asset 超過 16 MiB 限制。",
    "engineeringProgramming.targetInterface": "目標 / 介面",
    "engineeringProgramming.operation": "操作",
    "engineeringProgramming.state": "狀態",
    "engineeringProgramming.progress": "進度",
    "engineeringProgramming.independent": "獨立 E/P/V/R",
    "engineeringProgramming.selectedPpu": "選定 PPU",
    "engineeringProgramming.noFacility": "未選 Facility",
    "engineeringProgramming.noPpu": "未選 PPU",
    "engineeringProgramming.jobLog": "ENGINEERING JOB LOG",
    "engineeringProgramming.clear": "清除",
    "operation.erase": "擦除", "operation.program": "燒錄", "operation.verify": "驗證", "operation.read": "讀取",
  },
  "en-US": {
    "nav.entry": "Demo",
    "mode.label": "Product mode", "mode.production": "Production Mode", "mode.engineering": "Engineering Mode",
    "locale.zh": "繁中", "locale.en": "EN",
    "demo.eyebrow": "PLASMA PRODUCT ENTRY",
    "demo.title": "Choose Product Mode",
    "demo.lead": "PMode (Production Mode) is for production programming and batch operations; EMode (Engineering Mode) is for engineering development, validation, diagnostics, and configuration.",
    "demo.production.title": "Factory Production Console",
    "demo.production.description": "Factory operations view for multiple PPUs × Sites, PASS / FAIL status, batch selection, and Factory Log on one screen.",
    "demo.production.open": "Open Production Mode →",
    "demo.engineering.title": "Engineering Workspace",
    "demo.engineering.description": "Engineering and maintenance workspace for PPU / Sites, Programming, Diagnostics, Logs, Tools, and future low-level capabilities.",
    "demo.engineering.open": "Open Engineering Mode →",
    "demo.boundary.title": "Architecture boundary",
    "demo.boundary.description": "Manager aggregation failure does not stop local PPU programming.",
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
    "engineeringProgramming.workspace": "Engineering Programming workspace",
    "engineeringProgramming.title": "Single PPU Programming",
    "engineeringProgramming.subtitle": "Facility → PPU → Site; E/P/V/R is executed by the Python Engineering PPU Provider.",
    "engineeringProgramming.gateway": "Plasma Web REST Gateway",
    "engineeringProgramming.connect": "Connect",
    "engineeringProgramming.providerOffline": "PPU Provider offline",
    "engineeringProgramming.serverSource": "SERVER SOURCE OF TRUTH",
    "engineeringProgramming.serverSourceNote": "The browser does not create Mock topology; all target identities are reported by the Python Provider.",
    "engineeringProgramming.siteSelection": "Site Selection",
    "engineeringProgramming.selected": "Selected",
    "engineeringProgramming.imageAsset": "—",
    "engineeringProgramming.imageAssetHint": "Shared by Program / Verify · Max 16 MiB",
    "engineeringProgramming.browse": "Select Programming File",
    "engineeringProgramming.batchOperations": "Batch Operations",
    "engineeringProgramming.noSites": "No Sites selected",
    "engineeringProgramming.idle": "Idle",
    "engineeringProgramming.running": "Running",
    "engineeringProgramming.success": "Success",
    "engineeringProgramming.cancelled": "Cancelled",
    "engineeringProgramming.failed": "Failed",
    "engineeringProgramming.execute": "Execute",
    "engineeringProgramming.cancel": "Cancel",
    "engineeringProgramming.cancelling": "Cancelling",
    "engineeringProgramming.imageAssetTooLarge": "Programming Image Asset exceeds the 16 MiB limit.",
    "engineeringProgramming.targetInterface": "Target / Interface",
    "engineeringProgramming.operation": "Operation",
    "engineeringProgramming.state": "State",
    "engineeringProgramming.progress": "Progress",
    "engineeringProgramming.independent": "Independent E/P/V/R",
    "engineeringProgramming.selectedPpu": "Selected PPU",
    "engineeringProgramming.noFacility": "No Facility",
    "engineeringProgramming.noPpu": "No PPU",
    "engineeringProgramming.jobLog": "ENGINEERING JOB LOG",
    "engineeringProgramming.clear": "Clear",
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
  // SSR and the first client render both start in zh-TW. A persisted preference
  // is restored just after hydration. User actions drive React state directly.
  const [locale, setLocaleState] = useState<Locale>("zh-TW");
  const userSelected = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let persisted: Locale | null = null;
    try { persisted = normalizeLocale(window.localStorage.getItem(STORAGE_KEY)); } catch { /* storage is optional */ }

    queueMicrotask(() => {
      if (!cancelled && !userSelected.current && persisted) setLocaleState(persisted);
    });

    const syncFromStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setLocaleState(normalizeLocale(event.newValue));
    };
    window.addEventListener("storage", syncFromStorage);
    return () => {
      cancelled = true;
      window.removeEventListener("storage", syncFromStorage);
    };
  }, []);

  const setLocale = useCallback((next: Locale) => {
    userSelected.current = true;
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
