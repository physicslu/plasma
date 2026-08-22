"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { evaluateBatchReadiness } from "../batch-readiness";
import { beginBatchExecutionActivity } from "../batch-execution-activity";
import { useI18n } from "../i18n";
import {
  engineeringTargetApiBase,
  getEngineeringTargets,
  getPPUStatus,
} from "../plasma-api";
import type {
  EngineeringFacilityTarget,
  EngineeringPPUTarget,
  EngineeringTargetCatalog,
  Operation,
  SiteSnapshot,
} from "../plasma-api";
import {
  cancelServerBatch,
  cancelServerBatchPPU,
  createServerBatch,
  getServerBatch,
  terminalServerBatchStates,
} from "../server-batch-api";
import type {
  BatchExecutionPolicy,
  BatchSiteSnapshot,
  ServerBatchSiteState,
  ServerBatchSnapshot,
  ServerBatchState,
} from "../server-batch-api";
import { useWorkspaceSession, type SelectionMap } from "../workspace-session";
import { ActiveFpsSummary, BatchPolicyPanel, BatchTopologySummary } from "../batch-dashboard-panels";
import "../programming-batch-toolbar.css";
import "./fleet.css";
import "./production-prototype.css";
import "./operator-feedback.css";
import "./server-batch.css";

type SiteRunState = ServerBatchSiteState;
type BatchUiState = "idle" | ServerBatchState;
type SiteRuntime = {
  id: number;
  enabled: boolean;
  state: SiteRunState;
  progress: number;
  operation?: Operation;
  jobId?: string;
  error?: string;
  target?: string | null;
  interface?: string | null;
  currentRound: number;
  completedRounds: number;
  attempts: number;
  retries: number;
  finalFailures: number;
  failureSource?: string | null;
};
type PPURuntime = {
  facilityId: string;
  target: EngineeringPPUTarget;
  sites: SiteRuntime[];
  loading: boolean;
  error?: string;
};
type ActiveTarget = {
  key: string;
  facility: EngineeringFacilityTarget;
  target: EngineeringPPUTarget;
  siteIds: number[];
};
type LogEntry = { id: number; time: string; level: "INFO" | "WARN" | "ERROR"; text: string };

type StoredBatch = { apiBase: string; batchId: string };

const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const POLL_INTERVAL_MS = 250;
const POLL_LIMIT = 14_400;
const ACTIVE_BATCH_STORAGE_KEY = "plasma-production-active-batch-v1";
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };

const copy = {
  "zh-TW": {
    eyebrow: "PRODUCTION MODE · SERVER BATCH",
    title: "Factory Production Console",
    subtitle: "Facility → PPU → Site · Server-side Batch Runtime",
    provider: "Mock PPU Provider",
    loading: "正在連接 Mock Provider…",
    offline: "Mock Provider 無法使用。請確認 Plasma Web REST Gateway 已啟用 Engineering Mock Provider。",
    selector: "FPS 選擇",
    selectorHint: "多選 Facility / PPU / Site，按確定選取後才更新 Active FPS。",
    clearAll: "全部取消",
    selectAll: "全選",
    apply: "確定選取",
    collapse: "收起選擇器",
    expand: "展開選擇器",
    selectedOverview: "已選擇 FPS 總覽",
    selectedSites: "Sites",
    noSelection: "尚未選擇 FPS。",
    operations: "批次操作",
    imageHint: "未選 Image 時由 Mock Settings 的 Default Image Size 自動產生 Synthetic Image；手動選檔時以選檔優先。",
    browse: "選擇燒錄檔",
    syntheticImage: "Mock Synthetic Image",
    execute: "執行批次",
    cancelAll: "取消批次",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    faulted: "FAULTED",
    error: "ERROR",
    stopped: "STOPPED",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    queued: "QUEUED",
    stopping: "STOPPING",
    liveStatus: "Active FPS : 即時執行狀態",
    hierarchyHint: "依 Facility / PPU / Site 定位；執行 ownership 在 Gateway Batch Runtime",
    log: "Production Batch Log",
    clearLog: "清除 Log",
    imageTooLarge: "Programming Image 超過 Mock 4 MiB 上限。",
    chooseOperation: "未選擇任何操作。請至少選擇 Erase、Program、Verify 或 Read 其中一項。",
    dismissWarning: "關閉警告",
    noSelectedSites: "目前 FPS 集合沒有可執行的 Site。",
    loadFailed: "PPU 狀態載入失敗",
    repeatCount: "Repeat Count",
    retryLimit: "Site Retry Limit",
    stopThreshold: "Failed Site Stop Threshold",
    thresholdHint: "留空 = 不使用 threshold；達到門檻時 Batch → ERROR。",
    policyInvalid: "Batch Execution Policy 設定無效。",
    statistics: "Batch Statistics",
  },
  "en-US": {
    eyebrow: "PRODUCTION MODE · SERVER BATCH",
    title: "Factory Production Console",
    subtitle: "Facility → PPU → Site · Server-side Batch Runtime",
    provider: "Mock PPU Provider",
    loading: "Connecting to Mock Provider…",
    offline: "Mock Provider is unavailable. Enable the Engineering Mock Provider on the Plasma Web REST Gateway.",
    selector: "FPS Selection",
    selectorHint: "Select Facilities, PPUs, and Sites. Active FPS changes only after confirmation.",
    clearAll: "Cancel All",
    selectAll: "Select all",
    apply: "Confirm",
    collapse: "Collapse selector",
    expand: "Expand selector",
    selectedOverview: "Selected FPS Overview",
    selectedSites: "Sites",
    noSelection: "No FPS selected.",
    operations: "Batch Operations",
    imageHint: "Without a selected Image, Mock generates a Synthetic Image from Default Image Size; a selected file takes precedence.",
    browse: "Select Programming File",
    syntheticImage: "Mock Synthetic Image",
    execute: "Execute Batch",
    cancelAll: "Cancel Batch",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    faulted: "FAULTED",
    error: "ERROR",
    stopped: "STOPPED",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    queued: "QUEUED",
    stopping: "STOPPING",
    liveStatus: "Active FPS : Live Execution Status",
    hierarchyHint: "Locate by Facility / PPU / Site; execution ownership is in the Gateway Batch Runtime",
    log: "Production Batch Log",
    clearLog: "Clear Log",
    imageTooLarge: "Programming Image exceeds the 4 MiB Mock limit.",
    chooseOperation: "No operation selected. Select at least one of Erase, Program, Verify, or Read.",
    dismissWarning: "Dismiss warning",
    noSelectedSites: "The active FPS set has no executable Site.",
    loadFailed: "PPU status load failed",
    repeatCount: "Repeat Count",
    retryLimit: "Site Retry Limit",
    stopThreshold: "Failed Site Stop Threshold",
    thresholdHint: "Blank disables the threshold; reaching it terminates the Batch as ERROR.",
    policyInvalid: "Batch Execution Policy is invalid.",
    statistics: "Batch Statistics",
  },
} as const;

function nowTime(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function targetKey(facilityId: string, ppuId: string): string {
  return `${facilityId}::${ppuId}`;
}

function allSiteIds(ppu: EngineeringPPUTarget): number[] {
  return Array.from({ length: ppu.site_count }, (_, index) => index + 1);
}

function cloneSelection(selection: SelectionMap): SelectionMap {
  return Object.fromEntries(
    Object.entries(selection).map(([facilityId, ppus]) => [
      facilityId,
      Object.fromEntries(Object.entries(ppus).map(([ppuId, siteIds]) => [ppuId, [...siteIds].sort((a, b) => a - b)])),
    ]),
  );
}

function normalizeSelection(selection: SelectionMap): SelectionMap {
  const next: SelectionMap = {};
  for (const [facilityId, ppus] of Object.entries(selection)) {
    const selectedPpus = Object.fromEntries(
      Object.entries(ppus)
        .map(([ppuId, siteIds]) => [ppuId, [...new Set(siteIds)].sort((a, b) => a - b)] as const)
        .filter(([, siteIds]) => siteIds.length > 0),
    );
    if (Object.keys(selectedPpus).length > 0) next[facilityId] = selectedPpus;
  }
  return next;
}

function selectionCounts(selection: SelectionMap) {
  const facilities = Object.keys(selection).filter(facilityId => Object.keys(selection[facilityId] ?? {}).length > 0);
  const ppus = facilities.flatMap(facilityId => Object.keys(selection[facilityId] ?? {}));
  const sites = facilities.flatMap(facilityId => Object.values(selection[facilityId] ?? {}).flat());
  return { facilities: facilities.length, ppus: ppus.length, sites: sites.length };
}

function densityFor(siteCount: number): "spacious" | "comfortable" | "compact" | "dense" {
  if (siteCount <= 8) return "spacious";
  if (siteCount <= 16) return "comfortable";
  if (siteCount <= 32) return "compact";
  return "dense";
}

function orderedOperations(selected: Operation[]): Operation[] {
  return operationOrder.filter(operation => selected.includes(operation));
}

function runtimeFromStatus(snapshot: SiteSnapshot): SiteRuntime {
  const running = Boolean(snapshot.current_job_id) || snapshot.state === "queued" || snapshot.state === "running";
  return {
    id: snapshot.site_id,
    enabled: snapshot.enabled,
    state: running ? "running" : "ready",
    progress: 0,
    jobId: snapshot.current_job_id ?? undefined,
    target: snapshot.target,
    interface: snapshot.interface,
    currentRound: 0,
    completedRounds: 0,
    attempts: 0,
    retries: 0,
    finalFailures: 0,
  };
}

function runtimeFromBatchSite(site: BatchSiteSnapshot, previous?: SiteRuntime): SiteRuntime {
  return {
    id: site.site_id,
    enabled: previous?.enabled ?? true,
    state: site.state,
    progress: Math.round(site.progress_percent ?? 0),
    operation: site.current_operation ?? undefined,
    jobId: site.current_job_id ?? undefined,
    error: site.error?.message,
    target: previous?.target,
    interface: previous?.interface,
    currentRound: site.current_round,
    completedRounds: site.completed_rounds,
    attempts: site.total_attempts,
    retries: site.retry_count,
    finalFailures: site.final_failures,
    failureSource: site.last_failure_source,
  };
}

function selectionFromBatch(batch: ServerBatchSnapshot): SelectionMap {
  const selection: SelectionMap = {};
  for (const site of batch.sites) {
    selection[site.facility_id] ??= {};
    selection[site.facility_id][site.ppu_id] ??= [];
    selection[site.facility_id][site.ppu_id].push(site.site_id);
  }
  return normalizeSelection(selection);
}

function ppuStatus(runtime: PPURuntime): SiteRunState | "partial" {
  const sites = runtime.sites;
  if (sites.length === 0) return "ready";
  if (sites.some(site => site.state === "running")) return "running";
  if (sites.some(site => site.state === "error")) return "error";
  if (sites.some(site => site.state === "faulted")) return "faulted";
  if (sites.every(site => site.state === "success")) return "success";
  if (sites.every(site => site.state === "cancelled")) return "cancelled";
  if (sites.every(site => site.state === "stopped")) return "stopped";
  if (sites.every(site => site.state === "ready")) return "ready";
  return "partial";
}

function parsePositiveInt(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function parseNonNegativeInt(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function batchStateLevel(state: ServerBatchState): LogEntry["level"] {
  if (state === "error") return "ERROR";
  if (state === "cancelled" || state === "partial" || state === "stopping") return "WARN";
  return "INFO";
}

function readStoredBatch(): StoredBatch | null {
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_BATCH_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredBatch>;
    if (typeof value.apiBase !== "string" || typeof value.batchId !== "string") return null;
    return { apiBase: value.apiBase, batchId: value.batchId };
  } catch {
    return null;
  }
}

function writeStoredBatch(apiBase: string, batchId: string): void {
  try {
    window.sessionStorage.setItem(ACTIVE_BATCH_STORAGE_KEY, JSON.stringify({ apiBase, batchId } satisfies StoredBatch));
  } catch {
    // Session storage is an optional reconnect aid.
  }
}

function clearStoredBatch(): void {
  try { window.sessionStorage.removeItem(ACTIVE_BATCH_STORAGE_KEY); } catch { /* optional */ }
}

export default function ServerBatchFleetPage() {
  const { locale, t } = useI18n();
  const text = copy[locale];
const dashboardCopy = locale === "zh-TW" ? {
  policy: {
    repeatCount: "Repeat Count",
    retryLimit: "Site Retry Limit",
    stopThreshold: "Failed Site Stop Threshold",
    repeatTooltip: "整個 Batch 連續執行的輪數（1–10000）。",
    retryTooltip: "單一 Site 的操作失敗後最多重試次數（0–20）。",
    thresholdTooltip: "Retry 用盡後成為 FAULTED 的 Site 數達門檻時停止 Batch；off 表示不啟用。",
    hint: "Repeat 套用整個 Batch；Retry 只針對可信操作失敗；Threshold 只計入 Retry 用盡的 FAULTED Site。",
    invalid: "Batch Execution Policy 設定無效。",
  },
  active: {
    title: "Active FPS : 即時結果摘要",
    hint: "FAULTED = Retry 用盡的可信 DUT/Site 失敗；ERROR = 基礎設施或 Runtime 錯誤。",
    selected: "總選擇",
    running: "執行中",
    pass: "成功 (PASS)",
    faulted: "失敗 (FAULTED)",
    error: "錯誤 (ERROR)",
    stopped: "已停止",
    cancelled: "已取消",
  },
} : {
  policy: {
    repeatCount: "Repeat Count",
    retryLimit: "Site Retry Limit",
    stopThreshold: "Failed Site Stop Threshold",
    repeatTooltip: "Number of complete Batch rounds (1–10000).",
    retryTooltip: "Maximum retries after a trustworthy Site operation failure (0–20).",
    thresholdTooltip: "Stop the Batch when retry-exhausted FAULTED Sites reach this count; off disables the threshold.",
    hint: "Repeat applies to the whole Batch; Retry applies only to trustworthy operation failures; Threshold counts retry-exhausted FAULTED Sites.",
    invalid: "Batch Execution Policy is invalid.",
  },
  active: {
    title: "Active FPS : Live Result Summary",
    hint: "FAULTED = trustworthy DUT/Site failure after retry exhaustion; ERROR = infrastructure or runtime failure.",
    selected: "Selected",
    running: "Running",
    pass: "PASS",
    faulted: "FAULTED",
    error: "ERROR",
    stopped: "Stopped",
    cancelled: "Cancelled",
  },
};
  const {
    hydrated: workspaceHydrated,
    apiBase,
    engineeringSessionId: sessionId,
    ensureEngineeringSession,
    programmingImage: imageAsset,
    setProgrammingImage: setImageAsset,
    pmodDraftSelection: draftSelection,
    setPmodDraftSelection: setDraftSelection,
    pmodActiveSelection: activeSelection,
    setPmodActiveSelection: setActiveSelection,
    pmodOperations: selectedOperations,
    setPmodOperations: setSelectedOperations,
    pmodSelectorCollapsed: selectorCollapsed,
    setPmodSelectorCollapsed: setSelectorCollapsed,
  } = useWorkspaceSession();

  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<Record<string, PPURuntime>>({});
  const [operatorWarning, setOperatorWarning] = useState<string | null>(null);
  const [batchState, setBatchState] = useState<BatchUiState>("idle");
  const [batchSnapshot, setBatchSnapshot] = useState<ServerBatchSnapshot | null>(null);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [repeatCount, setRepeatCount] = useState("1");
  const [siteRetryLimit, setSiteRetryLimit] = useState("0");
  const [failedSiteThreshold, setFailedSiteThreshold] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const imageInputRef = useRef<HTMLInputElement>(null);
  const logSequence = useRef(0);
  const initialActiveSelection = useRef(activeSelection);
  const activityReleaseRef = useRef<(() => void) | null>(null);
  const pollGenerationRef = useRef(0);

  const appendLog = useCallback((textValue: string, level: LogEntry["level"] = "INFO") => {
    setLogs(current => [...current, {
      id: ++logSequence.current,
      time: nowTime(),
      level,
      text: textValue,
    }].slice(-500));
  }, []);

  const beginActivity = useCallback(() => {
    if (activityReleaseRef.current) return;
    activityReleaseRef.current = beginBatchExecutionActivity();
  }, []);

  const endActivity = useCallback(() => {
    activityReleaseRef.current?.();
    activityReleaseRef.current = null;
  }, []);

  const applyBatchSnapshot = useCallback((next: ServerBatchSnapshot, sourceCatalog: EngineeringTargetCatalog) => {
    setBatchSnapshot(next);
    setBatchState(next.state);
    setActiveBatchId(next.batch_id);
    const nextSelection = selectionFromBatch(next);
    setActiveSelection(nextSelection);
    setDraftSelection(nextSelection);

    setRuntimes(current => {
      const nextRuntimes: Record<string, PPURuntime> = {};
      for (const facility of sourceCatalog.facilities) {
        for (const target of facility.ppus) {
          const batchSites = next.sites.filter(site => site.facility_id === facility.facility_id && site.ppu_id === target.ppu_id);
          if (batchSites.length === 0) continue;
          const key = targetKey(facility.facility_id, target.ppu_id);
          const previous = current[key];
          const previousById = new Map((previous?.sites ?? []).map(site => [site.id, site]));
          nextRuntimes[key] = {
            facilityId: facility.facility_id,
            target,
            loading: false,
            sites: batchSites.map(site => runtimeFromBatchSite(site, previousById.get(site.site_id))),
          };
        }
      }
      return nextRuntimes;
    });
  }, [setActiveSelection, setDraftSelection]);

  const pollServerBatch = useCallback(async (
    batchId: string,
    sourceCatalog: EngineeringTargetCatalog,
    generation: number,
  ) => {
    let previousState: ServerBatchState | null = null;
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      if (pollGenerationRef.current !== generation) return;
      const next = await getServerBatch(apiBase, batchId);
      applyBatchSnapshot(next, sourceCatalog);
      if (next.state !== previousState) {
        appendLog(`[BAT] ${next.state.toUpperCase()} · ${next.batch_id}`, batchStateLevel(next.state));
        previousState = next.state;
      }
      if (terminalServerBatchStates.has(next.state)) {
        clearStoredBatch();
        endActivity();
        const counts = next.site_counts;
        appendLog(
          `[BAT] TERMINAL · ${next.state.toUpperCase()} · PASS ${counts.success ?? 0} · FAULTED ${counts.faulted ?? 0} · ERROR ${counts.error ?? 0} · STOPPED ${counts.stopped ?? 0} · CANCELLED ${counts.cancelled ?? 0}`,
          batchStateLevel(next.state),
        );
        return;
      }
      await delay(POLL_INTERVAL_MS);
    }
    endActivity();
    appendLog(`[BAT] OBSERVATION TIMEOUT · ${batchId}`, "ERROR");
  }, [apiBase, appendLog, applyBatchSnapshot, endActivity]);

  const loadSelectionRuntimes = useCallback(async (
    sourceCatalog: EngineeringTargetCatalog,
    selection: SelectionMap,
  ) => {
    const targets = sourceCatalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = selection[facility.facility_id]?.[target.ppu_id] ?? [];
      if (siteIds.length === 0) return [];
      return [{ facility, target, siteIds, key: targetKey(facility.facility_id, target.ppu_id) }];
    }));
    if (targets.length === 0) {
      setRuntimes({});
      return;
    }
    setRuntimes(Object.fromEntries(targets.map(item => [item.key, {
      facilityId: item.facility.facility_id,
      target: item.target,
      sites: [],
      loading: true,
    } satisfies PPURuntime])));
    const results = await Promise.allSettled(targets.map(async item => {
      const targetBase = engineeringTargetApiBase(apiBase, item.facility.facility_id, item.target.ppu_id);
      return { item, status: await getPPUStatus(targetBase) };
    }));
    setRuntimes(current => {
      const next = { ...current };
      results.forEach((result, index) => {
        const item = targets[index];
        if (result.status === "fulfilled") {
          const selectedIds = new Set(item.siteIds);
          next[item.key] = {
            facilityId: item.facility.facility_id,
            target: item.target,
            loading: false,
            sites: result.value.status.sites.filter(site => selectedIds.has(site.site_id)).map(runtimeFromStatus),
          };
        } else {
          next[item.key] = {
            facilityId: item.facility.facility_id,
            target: item.target,
            loading: false,
            sites: [],
            error: result.reason instanceof Error ? result.reason.message : text.loadFailed,
          };
        }
      });
      return next;
    });
  }, [apiBase, text.loadFailed]);

  useEffect(() => {
    if (!workspaceHydrated) return;
    let stopped = false;
    void (async () => {
      try {
        await ensureEngineeringSession(apiBase);
        const nextCatalog = await getEngineeringTargets(apiBase);
        if (stopped) return;
        setCatalog(nextCatalog);
        setProviderError(null);
        appendLog(`[PROVIDER] ${nextCatalog.provider.toUpperCase()} · ${nextCatalog.facility_count} Facilities · ${nextCatalog.ppu_count} PPUs · ${nextCatalog.site_count} Sites`);

        const stored = readStoredBatch();
        if (stored?.apiBase === apiBase) {
          try {
            const restoredBatch = await getServerBatch(apiBase, stored.batchId);
            if (stopped) return;
            applyBatchSnapshot(restoredBatch, nextCatalog);
            if (!terminalServerBatchStates.has(restoredBatch.state)) {
              beginActivity();
              const generation = ++pollGenerationRef.current;
              appendLog(`[BAT] RESTORED · ${restoredBatch.batch_id} · ${restoredBatch.state.toUpperCase()}`);
              void pollServerBatch(restoredBatch.batch_id, nextCatalog, generation).catch(error => {
                endActivity();
                appendLog(`[BAT] OBSERVATION ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
              });
              return;
            }
            clearStoredBatch();
          } catch {
            clearStoredBatch();
          }
        }

        const restoredSelection = normalizeSelection(cloneSelection(initialActiveSelection.current));
        if (selectionCounts(restoredSelection).sites > 0) {
          await loadSelectionRuntimes(nextCatalog, restoredSelection);
          if (!stopped) appendLog(`[FPS] RESTORED · ${selectionCounts(restoredSelection).facilities} Facilities · ${selectionCounts(restoredSelection).ppus} PPUs · ${selectionCounts(restoredSelection).sites} Sites`);
        }
      } catch (error) {
        if (stopped) return;
        const detail = error instanceof Error ? error.message : "Mock Provider unavailable";
        setProviderError(detail);
        setCatalog(null);
        appendLog(`[PROVIDER] unavailable · ${detail}`, "ERROR");
      }
    })();
    return () => {
      stopped = true;
      pollGenerationRef.current += 1;
      endActivity();
    };
  }, [apiBase, appendLog, applyBatchSnapshot, beginActivity, endActivity, ensureEngineeringSession, loadSelectionRuntimes, pollServerBatch, workspaceHydrated]);

  const batchRunning = batchState === "queued" || batchState === "running" || batchState === "stopping";
  const draftCounts = useMemo(() => selectionCounts(draftSelection), [draftSelection]);
  const activeCounts = useMemo(() => selectionCounts(activeSelection), [activeSelection]);

  const activeTargets = useMemo<ActiveTarget[]>(() => {
    if (!catalog) return [];
    return catalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = activeSelection[facility.facility_id]?.[target.ppu_id] ?? [];
      if (siteIds.length === 0) return [];
      return [{ key: targetKey(facility.facility_id, target.ppu_id), facility, target, siteIds }];
    }));
  }, [activeSelection, catalog]);

  const groupedActiveTargets = useMemo(() => {
    if (!catalog) return [];
    return catalog.facilities.map(facility => ({
      facility,
      targets: activeTargets.filter(item => item.facility.facility_id === facility.facility_id),
    })).filter(group => group.targets.length > 0);
  }, [activeTargets, catalog]);

  const summary = useMemo(() => {
    const sites = Object.values(runtimes).flatMap(runtime => runtime.sites);
    const count = (state: SiteRunState) => sites.filter(site => site.state === state).length;
    return {
      facilities: activeCounts.facilities,
      ppus: activeCounts.ppus,
      sites: activeCounts.sites,
      running: count("running"),
      success: count("success"),
      faulted: count("faulted"),
      error: count("error"),
      stopped: count("stopped"),
      cancelled: count("cancelled"),
    };
  }, [activeCounts, runtimes]);

  const repeatValue = parsePositiveInt(repeatCount);
  const retryValue = parseNonNegativeInt(siteRetryLimit);
  const thresholdValue = failedSiteThreshold.trim() === "" ? null : parsePositiveInt(failedSiteThreshold);
  const policyValid = repeatValue !== null
    && repeatValue <= 10_000
    && retryValue !== null
    && retryValue <= 20
    && (failedSiteThreshold.trim() === "" || (thresholdValue !== null && thresholdValue <= activeCounts.sites));
  const executionPolicy: BatchExecutionPolicy | null = policyValid ? {
    repeat_count: repeatValue!,
    site_retry_limit: retryValue!,
    failed_site_stop_threshold: thresholdValue,
  } : null;

  const siteDensity = densityFor(summary.sites);
  const requiresImage = selectedOperations.some(operation => operation === "program" || operation === "verify");
  const syntheticMockImageAvailable = catalog?.provider === "mock";
  const allSitesExecutable = activeTargets.length > 0 && activeTargets.every(active => {
    const runtime = runtimes[active.key];
    return Boolean(
      runtime
      && !runtime.loading
      && !runtime.error
      && runtime.sites.length === active.siteIds.length
      && runtime.sites.every(site => site.enabled && site.state !== "running"),
    );
  });
  const batchReadiness = evaluateBatchReadiness({
    providerOnline: Boolean(catalog && !providerError),
    targetValid: activeTargets.length > 0,
    selectedSiteCount: activeCounts.sites,
    selectedOperationCount: selectedOperations.length,
    requiresImage,
    imagePresent: Boolean(imageAsset) || syntheticMockImageAvailable,
    imageValid: !imageAsset || imageAsset.size <= MAX_IMAGE_BYTES,
    readSelected: selectedOperations.includes("read"),
    readParamsValid: true,
    allSitesExecutable,
    batchRunning: batchState === "queued" || batchState === "running",
    batchCancelling: batchState === "stopping",
  });

  function selectedSiteIds(facilityId: string, ppuId: string): number[] {
    return draftSelection[facilityId]?.[ppuId] ?? [];
  }

  function setPpuSites(facilityId: string, ppuId: string, siteIds: number[]) {
    if (batchRunning) return;
    setDraftSelection(current => normalizeSelection({
      ...current,
      [facilityId]: { ...(current[facilityId] ?? {}), [ppuId]: siteIds },
    }));
  }

  function toggleFacility(facility: EngineeringFacilityTarget) {
    if (batchRunning) return;
    const allSelected = facility.ppus.every(ppu => selectedSiteIds(facility.facility_id, ppu.ppu_id).length === ppu.site_count);
    setDraftSelection(current => {
      const next = cloneSelection(current);
      if (allSelected) delete next[facility.facility_id];
      else next[facility.facility_id] = Object.fromEntries(facility.ppus.map(ppu => [ppu.ppu_id, allSiteIds(ppu)]));
      return normalizeSelection(next);
    });
  }

  function togglePpu(facilityId: string, ppu: EngineeringPPUTarget) {
    const current = selectedSiteIds(facilityId, ppu.ppu_id);
    setPpuSites(facilityId, ppu.ppu_id, current.length === ppu.site_count ? [] : allSiteIds(ppu));
  }

  function toggleSite(facilityId: string, ppu: EngineeringPPUTarget, siteId: number) {
    const current = selectedSiteIds(facilityId, ppu.ppu_id);
    const next = current.includes(siteId) ? current.filter(id => id !== siteId) : [...current, siteId];
    setPpuSites(facilityId, ppu.ppu_id, next);
  }

  function selectEverything() {
    if (!catalog || batchRunning) return;
    setDraftSelection(Object.fromEntries(catalog.facilities.map(facility => [
      facility.facility_id,
      Object.fromEntries(facility.ppus.map(ppu => [ppu.ppu_id, allSiteIds(ppu)])),
    ])));
  }

  function clearEverything() {
    if (batchRunning) return;
    setDraftSelection({});
  }

  async function applyFpsSelection() {
    if (!catalog || draftCounts.sites === 0 || batchRunning) return;
    const snapshot = normalizeSelection(cloneSelection(draftSelection));
    setActiveSelection(snapshot);
    setBatchState("idle");
    setBatchSnapshot(null);
    setActiveBatchId(null);
    setOperatorWarning(null);
    clearStoredBatch();
    appendLog(`[FPS] CONFIRM · ${selectionCounts(snapshot).facilities} Facilities · ${selectionCounts(snapshot).ppus} PPUs · ${selectionCounts(snapshot).sites} Sites`);
    await loadSelectionRuntimes(catalog, snapshot);
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setOperatorWarning(null);
    setSelectedOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : [...current, operation]);
  }

  async function executeBatch() {
    if (!catalog || batchRunning || activeTargets.length === 0) return;
    if (!batchReadiness.ready) {
      if (batchReadiness.code === "no-op") setOperatorWarning(text.chooseOperation);
      appendLog(`[BAT] BLOCKED · ${batchReadiness.label}`, "WARN");
      return;
    }
    if (!executionPolicy) {
      setOperatorWarning(text.policyInvalid);
      appendLog(`[BAT] BLOCKED · ${text.policyInvalid}`, "WARN");
      return;
    }
    const operations = orderedOperations(selectedOperations);
    const targets = activeTargets.map(active => ({
      facility_id: active.facility.facility_id,
      ppu_id: active.target.ppu_id,
      site_ids: [...active.siteIds],
    }));
    if (targets.length === 0) {
      appendLog(`[BAT] BLOCKED · ${text.noSelectedSites}`, "WARN");
      return;
    }

    setOperatorWarning(null);
    beginActivity();
    setBatchState("queued");
    appendLog(`[BAT] SUBMIT · ${summary.facilities} Facilities · ${summary.ppus} PPUs · ${summary.sites} Sites · ${operations.map(operation => operation.toUpperCase()).join(" → ")} · repeat ${executionPolicy.repeat_count} · retry ${executionPolicy.site_retry_limit} · threshold ${executionPolicy.failed_site_stop_threshold ?? "off"}`);
    try {
      const accepted = await createServerBatch(apiBase, {
        sessionId,
        targets,
        operations,
        executionPolicy,
        assetFile: imageAsset,
        allowSyntheticMockImage: syntheticMockImageAvailable,
        readOffset: 0,
        readLength: 256,
      });
      if (!imageAsset && accepted.asset) {
        appendLog(`[IMG] SYNTHETIC · ${accepted.asset.name} · ${accepted.asset.size_bytes} bytes`);
      }
      applyBatchSnapshot(accepted, catalog);
      writeStoredBatch(apiBase, accepted.batch_id);
      const generation = ++pollGenerationRef.current;
      appendLog(`[BAT] ACCEPTED · ${accepted.batch_id}`);
      void pollServerBatch(accepted.batch_id, catalog, generation).catch(error => {
        endActivity();
        appendLog(`[BAT] OBSERVATION ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
      });
    } catch (error) {
      endActivity();
      setBatchState("idle");
      const detail = error instanceof Error ? error.message : "Batch submission failed";
      setOperatorWarning(detail);
      appendLog(`[BAT] SUBMISSION ERROR · ${detail}`, "ERROR");
    }
  }

  async function cancelBatch() {
    if (!activeBatchId || !batchRunning || batchState === "stopping") return;
    setBatchState("stopping");
    appendLog(`[BAT] CANCEL REQUESTED · ${activeBatchId}`, "WARN");
    try {
      const next = await cancelServerBatch(apiBase, activeBatchId);
      if (catalog) applyBatchSnapshot(next, catalog);
    } catch (error) {
      appendLog(`[BAT] CANCEL ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
    }
  }

  async function cancelPPU(active: ActiveTarget) {
    if (!activeBatchId || !batchRunning) return;
    appendLog(`[PPU] CANCEL REQUESTED · ${active.key}`, "WARN");
    try {
      const next = await cancelServerBatchPPU(
        apiBase,
        activeBatchId,
        active.facility.facility_id,
        active.target.ppu_id,
      );
      if (catalog) applyBatchSnapshot(next, catalog);
    } catch (error) {
      appendLog(`[PPU] CANCEL ERROR · ${active.key} · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
    }
  }

  function siteStateText(site: SiteRuntime): string {
    if (site.state === "faulted") return "FAULTED — Retry Exhausted";
    if (site.state === "error") return "ERROR — Infrastructure";
    if (site.state === "stopped") return "STOPPED — Batch Policy";
    if (site.state === "cancelled") return text.cancelled;
    if (site.state === "success") return text.success;
    if (site.state === "running") return text.running;
    return text.ready;
  }

  return (
    <main className="productionPrototypePage">
      <section className="productionPrototypeShell">
        <header className="productionPrototypeHeading">
          <div><p>{text.eyebrow}</p><h1>{text.title}</h1><span>{text.subtitle}</span></div>
          <div className={`prototypeProvider ${providerError ? "offline" : catalog ? "online" : "loading"}`}>
            <i /><div><small>{text.provider}</small><b>{providerError ? "OFFLINE" : catalog ? "ONLINE" : "CONNECTING"}</b></div>
          </div>
        </header>

        {!catalog && (
          <section className="prototypeNotice" role="status">
            <b>{providerError ? text.offline : text.loading}</b>
            {providerError && <span>{providerError}</span>}
          </section>
        )}

        {catalog && (
          <div className={`productionWorkspace ${selectorCollapsed ? "selector-collapsed" : ""}`}>
            <aside className="fpsSelector" aria-label="FPS selector tree">
              <button type="button" className="fpsSelectorCollapse" aria-label={selectorCollapsed ? text.expand : text.collapse} onClick={() => setSelectorCollapsed(current => !current)}>
                {selectorCollapsed ? "›" : "‹"}
              </button>

              {!selectorCollapsed && (
                <>
                  <header className="fpsSelectorHead"><div><h2>{text.selector}</h2><span>{text.selectorHint}</span></div></header>
                  <div className="fpsSelectorActions">
                    <div className="fpsSelectorCommandGroup">
                      <button type="button" onClick={selectEverything} disabled={batchRunning}>{text.selectAll}</button>
                      <button type="button" className="cancelDraftButton" onClick={clearEverything} disabled={batchRunning || draftCounts.sites === 0}>{text.clearAll}</button>
                      <button type="button" className="confirmFpsButton" onClick={() => void applyFpsSelection()} disabled={draftCounts.sites === 0 || batchRunning}>{text.apply}</button>
                    </div>
                    <div><b>{draftCounts.facilities}</b> F / <b>{draftCounts.ppus}</b> P / <b>{draftCounts.sites}</b> S</div>
                  </div>

                  <div className="fpsTree">
                    {catalog.facilities.map(facility => {
                      const facilitySelectedSites = facility.ppus.reduce((count, ppu) => count + selectedSiteIds(facility.facility_id, ppu.ppu_id).length, 0);
                      const facilityTotalSites = facility.ppus.reduce((count, ppu) => count + ppu.site_count, 0);
                      const facilityChecked = facilitySelectedSites === facilityTotalSites && facilityTotalSites > 0;
                      return (
                        <section className="fpsFacilityNode" key={facility.facility_id}>
                          <label className="fpsFacilityRow">
                            <input type="checkbox" checked={facilityChecked} disabled={batchRunning} onChange={() => toggleFacility(facility)} />
                            <span><b>{facility.display_name}</b><small>{facilitySelectedSites}/{facilityTotalSites} Sites</small></span>
                          </label>
                          <div className="fpsPpuList">
                            {facility.ppus.map(ppu => {
                              const siteIds = selectedSiteIds(facility.facility_id, ppu.ppu_id);
                              const ppuChecked = siteIds.length === ppu.site_count && ppu.site_count > 0;
                              return (
                                <div className="fpsPpuNode" key={ppu.ppu_id}>
                                  <label className="fpsPpuRow">
                                    <input type="checkbox" checked={ppuChecked} disabled={batchRunning} onChange={() => togglePpu(facility.facility_id, ppu)} />
                                    <span><b>{ppu.display_name}</b><small>{siteIds.length}/{ppu.site_count} Sites</small></span>
                                  </label>
                                  <div className="fpsSiteChoiceGrid">
                                    {allSiteIds(ppu).map(siteId => {
                                      const checked = siteIds.includes(siteId);
                                      return (
                                        <label className={checked ? "selected" : ""} key={siteId}>
                                          <input
                                            type="checkbox"
                                            aria-label={`${facility.facility_id} ${ppu.ppu_id} ${siteLabel(siteId)}`}
                                            checked={checked}
                                            disabled={batchRunning}
                                            onChange={() => toggleSite(facility.facility_id, ppu, siteId)}
                                          />
                                          <span>{siteLabel(siteId)}</span>
                                        </label>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </section>
                      );
                    })}
                  </div>

                  <section className="fpsSelectionSummary" aria-label={text.selectedOverview}>
                    <header><b>{text.selectedOverview}</b><span>{draftCounts.facilities} F / {draftCounts.ppus} P / {draftCounts.sites} S</span></header>
                    {draftCounts.sites === 0 ? <p>{text.noSelection}</p> : <div className="fpsSelectionChips" />}
                  </section>
                </>
              )}
            </aside>

            <section className="productionMainPanel">
              <BatchTopologySummary
      facilityCount={catalog.facility_count}
      ppuCount={catalog.ppu_count}
      selectedSiteCount={summary.sites}
      selectedFacilityCount={summary.facilities}
      selectedPpuCount={summary.ppus}
      counts={{ selected: summary.sites, running: summary.running, pass: summary.success, faulted: summary.faulted, error: summary.error, stopped: summary.stopped, cancelled: summary.cancelled }}
    />

    <section className="unifiedBatchControlStack" data-dashboard-mode="production">
    <section className="productionBatchToolbar programmingBatchToolbar" aria-label="Batch operation toolbar">
                <div className="productionImagePicker programmingBatchFile">
                  <button type="button" className="productionBrowseButton" disabled={batchRunning} onClick={() => imageInputRef.current?.click()}>{text.browse}</button>
                  <input
                    ref={imageInputRef}
                    aria-label="Production Programming Image file"
                    type="file"
                    accept=".bin,application/octet-stream"
                    hidden
                    disabled={batchRunning}
                    onChange={event => {
                      const file = event.target.files?.[0] ?? null;
                      if (file && file.size > MAX_IMAGE_BYTES) {
                        appendLog(`[IMG] BLOCKED · ${text.imageTooLarge}`, "WARN");
                        event.currentTarget.value = "";
                        setImageAsset(null);
                      } else {
                        setImageAsset(file);
                        if (file) appendLog(`[IMG] SELECTED · ${file.name} · ${file.size} bytes`);
                      }
                    }}
                  />
                  <em
                    className="programmingFileName"
                    data-image-source={imageAsset ? "user" : requiresImage && syntheticMockImageAvailable ? "mock_synthetic" : "none"}
                    title={imageAsset?.name}
                  >
                    {imageAsset?.name ?? (requiresImage && syntheticMockImageAvailable ? text.syntheticImage : "—")}
                  </em>
                  <small className="programmingFileHint">{text.imageHint}</small>
                </div>

                <div className="batchOperations programmingBatchOperations">
                  <span>{text.operations}</span>
                  {operationOrder.map(operation => (
                    <label key={operation}>
                      <input type="checkbox" checked={selectedOperations.includes(operation)} disabled={batchRunning} onChange={() => toggleOperation(operation)} />
                      <b>{operationCodes[operation]}</b> {t(`operation.${operation}`)}
                    </label>
                  ))}
                </div>

                <div className="productionBatchActions programmingBatchActions">
                  <div className={`batchState batchReadiness readiness-${batchReadiness.code}`} role="status" aria-label="Batch readiness">
                    <small>BATCH</small><b>{batchRunning ? String(batchState).toUpperCase() : batchReadiness.label}</b>
                  </div>
                  <button type="button" className="executeBatchButton" onClick={() => void executeBatch()} disabled={!batchReadiness.ready || !policyValid}>{text.execute}</button>
                  <button type="button" className="cancelBatchButton" onClick={() => void cancelBatch()} disabled={!batchRunning || batchState === "stopping"}>{text.cancelAll}</button>
                </div>
              </section>

              <BatchPolicyPanel
      repeatCount={repeatCount}
      retryLimit={siteRetryLimit}
      stopThreshold={failedSiteThreshold}
      maxThreshold={activeCounts.sites}
      disabled={batchRunning}
      valid={policyValid}
      copy={dashboardCopy.policy}
      onRepeatCount={setRepeatCount}
      onRetryLimit={setSiteRetryLimit}
      onStopThreshold={setFailedSiteThreshold}
    />
    </section>

    <ActiveFpsSummary
      counts={{ selected: summary.sites, running: summary.running, pass: summary.success, faulted: summary.faulted, error: summary.error, stopped: summary.stopped, cancelled: summary.cancelled }}
      copy={dashboardCopy.active}
    />

              {batchSnapshot && (
                <section className={`serverBatchStatistics state-${batchSnapshot.state}`} aria-label={text.statistics} data-batch-id={batchSnapshot.batch_id} data-batch-state={batchSnapshot.state}>
                  <header>
                    <div><small>BATCH ID</small><code>{batchSnapshot.batch_id}</code></div>
                    <div><small>STATE</small><b>{batchSnapshot.state.toUpperCase()}</b></div>
                    <div><small>FAULTED</small><b>{batchSnapshot.faulted_site_count}</b></div>
                    <div><small>POLICY</small><b>R×{batchSnapshot.execution_policy.repeat_count} · Retry {batchSnapshot.execution_policy.site_retry_limit} · Stop {batchSnapshot.execution_policy.failed_site_stop_threshold ?? "off"}</b></div>
                  </header>
                  <div className="operationStatisticsGrid">
                    {batchSnapshot.operations.map(operation => {
                      const stats = batchSnapshot.operation_statistics[operation];
                      if (!stats) return null;
                      return (
                        <article key={operation} data-operation-stat={operation}>
                          <b>{operationCodes[operation]} · {t(`operation.${operation}`)}</b>
                          <span>Logical <strong>{stats.logical_executions}</strong></span>
                          <span>Attempts <strong>{stats.attempts}</strong></span>
                          <span>Retries <strong>{stats.retries}</strong></span>
                          <span>Failed attempts <strong>{stats.failed_attempts}</strong></span>
                        </article>
                      );
                    })}
                  </div>
                  {batchSnapshot.error?.message && <p className="batchRuntimeError">{batchSnapshot.error.error_code ? `${batchSnapshot.error.error_code} · ` : ""}{batchSnapshot.error.message}</p>}
                </section>
              )}

              {operatorWarning && (
                <div className="productionOperationWarning" role="alert">
                  <span>{operatorWarning}</span>
                  <button type="button" aria-label={text.dismissWarning} onClick={() => setOperatorWarning(null)}>×</button>
                </div>
              )}

              <section className={`productionRuntimeBoard density-${siteDensity}`} aria-label={text.liveStatus}>
                <header className="runtimeBoardHead">
                  <div><h2>{text.liveStatus}</h2><span>{text.hierarchyHint}</span></div>
                  <div className="runtimeLegend">
                    <span><i className="ready" /> READY</span><span><i className="running" /> RUNNING</span><span><i className="success" /> PASS</span><span><i className="faulted" /> FAULTED</span><span><i className="error" /> ERROR</span><span><i className="stopped" /> STOPPED</span><span><i className="cancelled" /> CANCELLED</span>
                  </div>
                </header>

                {groupedActiveTargets.length === 0 ? <div className="emptyProductionSet">{text.noSelection}</div> : (
                  <div className="facilityRuntimeStack">
                    {groupedActiveTargets.map(group => {
                      const facilitySiteCount = group.targets.reduce((count, active) => count + active.siteIds.length, 0);
                      return (
                        <section className="facilityRuntimeGroup" data-production-facility={group.facility.facility_id} key={group.facility.facility_id}>
                          <header><div className="facilityRuntimeIdentity"><i /><h3>{group.facility.display_name}</h3></div><span>{group.targets.length} PPU · {facilitySiteCount} Sites</span></header>
                          <div className="facilityRuntimePpuGrid">
                            {group.targets.map(active => {
                              const runtime = runtimes[active.key];
                              const status = runtime ? ppuStatus(runtime) : "ready";
                              const statusText = status === "partial" ? text.partial : text[status];
                              return (
                                <article className={`productionPpuPrototype ppu-${status}`} data-production-ppu={active.target.ppu_id} data-production-target={active.key} key={active.key}>
                                  <header>
                                    <div className="productionPpuIdentity"><i /><div><h4>{active.target.display_name}</h4><small>{active.target.ppu_id}</small></div></div>
                                    <div className="productionPpuMeta"><b>{statusText}</b><span>{active.siteIds.length} Sites</span></div>
                                    <button type="button" className="cancelPpuButton" onClick={() => void cancelPPU(active)} disabled={!batchRunning}>Cancel PPU</button>
                                  </header>
                                  {runtime?.loading && <div className="ppuLoading">Loading {active.target.ppu_id}…</div>}
                                  {runtime?.error && <div className="ppuError">{runtime.error}</div>}
                                  {runtime && !runtime.loading && !runtime.error && (
                                    <div className="productionSitePrototypeGrid">
                                      {runtime.sites.map(site => (
                                        <article
                                          className={`productionSitePrototype site-${site.state}`}
                                          data-production-site={site.id}
                                          data-site-state={site.state}
                                          data-completed-rounds={site.completedRounds}
                                          data-total-attempts={site.attempts}
                                          key={site.id}
                                          title={`${group.facility.display_name} / ${active.target.display_name} / ${siteLabel(site.id)}`}
                                        >
                                          <b>{siteLabel(site.id)}</b>
                                          <div className={`prototypeSiteLamp ${site.state}`}><i /></div>
                                          <strong>{siteStateText(site)}</strong>
                                          {site.operation && <small>{operationCodes[site.operation]} · {t(`operation.${site.operation}`)}{site.state === "running" ? ` · ${site.progress}%` : ""}</small>}
                                          {(site.currentRound > 0 || site.completedRounds > 0) && <small>Round {Math.max(site.currentRound, site.completedRounds)}/{batchSnapshot?.execution_policy.repeat_count ?? 1}</small>}
                                          {(site.attempts > 0 || site.retries > 0) && <small>Attempts {site.attempts} · Retry {site.retries}</small>}
                                          {site.failureSource && <small>Source · {site.failureSource}</small>}
                                        </article>
                                      ))}
                                    </div>
                                  )}
                                </article>
                              );
                            })}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                )}
              </section>

              <details className="productionPrototypeLog">
                <summary>{text.log} <span>{logs.length}</span></summary>
                <header><button type="button" onClick={() => setLogs([])}>{text.clearLog}</button></header>
                <div className="prototypeLogBody">
                  {logs.length === 0 && <div className="prototypeEmptyLog">—</div>}
                  {logs.map(entry => <div className={`prototypeLogRow level-${entry.level.toLowerCase()}`} key={entry.id}><span>{entry.time}</span><b>{entry.level}</b><code>{entry.text}</code></div>)}
                </div>
              </details>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}
