"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { evaluateBatchReadiness } from "../batch-readiness";
import { beginBatchExecutionActivity, notifyBatchExecutionActivityChanged } from "../batch-execution-activity";
import type { DeviceSearchResult } from "../device-catalog-api";
import { ICPickerField } from "../devices/ic-picker-field";
import { useI18n } from "../i18n";
import { OperatorKpiStrip, OperatorPanel } from "../operator-ui/operator-panel";
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
import ProductionLogPanel, { type ProductionLogEntry } from "./production-log-panel";
import "./factory-console-v2.css";

type SiteRunState = ServerBatchSiteState;
type BatchCommandState = "idle" | "submitting" | "aborting";
type BatchObservationState = "connected" | "reconnecting";
type LogEntry = ProductionLogEntry;

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

type ProductionTarget = {
  key: string;
  facility: EngineeringFacilityTarget;
  target: EngineeringPPUTarget;
  siteIds: number[];
};

type StoredBatch = { apiBase: string; batchId: string };

const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const POLL_INTERVAL_MS = 250;
const POLL_LIMIT = 14_400;
const ACTIVE_BATCH_STORAGE_KEY = "plasma-production-active-batch-v1";
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };

const copy = {
  "zh-TW": {
    title: "PMODE · FACTORY CONSOLE",
    provider: "Mock PPU Provider",
    loading: "正在連接 Mock Provider…",
    offline: "Mock Provider 無法使用。請確認 Plasma Web REST Gateway 已啟用 Mock Provider。",
    productionSelection: "PRODUCTION SITE SELECTION",
    productionSelectionHint: "Tree 定義 Production Set；進入量產後仍可在 Live Site Status 決定下一個 Batch 的 PPU / Site membership。",
    showSelection: "展開",
    hideSelection: "收起",
    selectAll: "全選",
    clearAll: "全部取消",
    applySet: "SET PRODUCTION SITES",
    productionSet: "Production Set",
    noProductionSet: "尚未建立 Production Set。",
    programmingJob: "PROGRAMMING JOB",
    targetIc: "Target IC",
    image: "Programming Image",
    imageHint: "Mock 可使用 Synthetic Image；手動選擇 .bin 時以選檔優先。",
    browse: "Browse…",
    operations: "Operations",
    batchPolicy: "Batch Policy",
    repeat: "Repeat",
    retry: "Retry",
    stopPolicy: "Stop Policy",
    never: "Never",
    start: "START PROGRAMMING",
    abort: "ABORT",
    batchStatus: "BATCH STATUS",
    liveStatus: "LIVE SITE STATUS",
    liveHint: "Checkbox 決定下一個 Batch；START 後 membership 鎖定，執行中只允許整批 ABORT。",
    factoryLog: "FACTORY LOG",
    clearLog: "清除 Log",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    faulted: "FAIL",
    error: "ERROR",
    stopped: "STOPPED",
    cancelled: "CANCELLED",
    disabled: "DISABLED",
    partial: "PARTIAL",
    imageTooLarge: "Programming Image 超過 4 MiB 上限。",
    chooseOperation: "至少選擇一項 E / P / V / R 操作。",
    chooseTarget: "量產 Batch 必須選擇 Target IC。",
    chooseBatchSite: "至少勾選一個 Batch Site。",
    policyInvalid: "Batch Policy 設定無效。",
    loadFailed: "PPU 狀態載入失敗",
    batchSelectionLocked: "Batch 執行中，PPU / Site membership 已鎖定；只能使用整批 ABORT。",
  },
  "en-US": {
    title: "PMODE · FACTORY CONSOLE",
    provider: "Mock PPU Provider",
    loading: "Connecting to Mock Provider…",
    offline: "Mock Provider is unavailable. Enable the Mock Provider on the Plasma Web REST Gateway.",
    productionSelection: "PRODUCTION SITE SELECTION",
    productionSelectionHint: "The tree defines the Production Set. Live Site Status independently defines the next Batch PPU / Site membership.",
    showSelection: "Show",
    hideSelection: "Hide",
    selectAll: "Select All",
    clearAll: "Clear All",
    applySet: "SET PRODUCTION SITES",
    productionSet: "Production Set",
    noProductionSet: "No Production Set has been committed.",
    programmingJob: "PROGRAMMING JOB",
    targetIc: "Target IC",
    image: "Programming Image",
    imageHint: "Mock can use a Synthetic Image; a selected .bin file takes precedence.",
    browse: "Browse…",
    operations: "Operations",
    batchPolicy: "Batch Policy",
    repeat: "Repeat",
    retry: "Retry",
    stopPolicy: "Stop Policy",
    never: "Never",
    start: "START PROGRAMMING",
    abort: "ABORT",
    batchStatus: "BATCH STATUS",
    liveStatus: "LIVE SITE STATUS",
    liveHint: "Checkboxes define the next Batch. Membership is immutable after START; only whole-Batch ABORT is allowed while running.",
    factoryLog: "FACTORY LOG",
    clearLog: "Clear Log",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    faulted: "FAIL",
    error: "ERROR",
    stopped: "STOPPED",
    cancelled: "CANCELLED",
    disabled: "DISABLED",
    partial: "PARTIAL",
    imageTooLarge: "Programming Image exceeds the 4 MiB limit.",
    chooseOperation: "Select at least one E / P / V / R operation.",
    chooseTarget: "Production Batch requires a Target IC.",
    chooseBatchSite: "Select at least one Batch Site.",
    policyInvalid: "Batch Policy is invalid.",
    loadFailed: "PPU status load failed",
    batchSelectionLocked: "Batch membership is locked while running; only whole-Batch ABORT is available.",
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

function selectionFromBatch(batch: ServerBatchSnapshot): SelectionMap {
  const selection: SelectionMap = {};
  for (const site of batch.sites) {
    selection[site.facility_id] ??= {};
    selection[site.facility_id][site.ppu_id] ??= [];
    selection[site.facility_id][site.ppu_id].push(site.site_id);
  }
  return normalizeSelection(selection);
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

function densityFor(siteCount: number): "spacious" | "comfortable" | "compact" | "dense" {
  if (siteCount <= 8) return "spacious";
  if (siteCount <= 20) return "comfortable";
  if (siteCount <= 40) return "compact";
  return "dense";
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
    notifyBatchExecutionActivityChanged();
  } catch { /* optional */ }
}

function clearStoredBatch(): void {
  try {
    window.sessionStorage.removeItem(ACTIVE_BATCH_STORAGE_KEY);
    notifyBatchExecutionActivityChanged();
  } catch { /* optional */ }
}

function formatBatchTime(snapshot: ServerBatchSnapshot | null, now: number): string {
  if (!snapshot?.started_at) return "00:00:00";
  const start = Date.parse(snapshot.started_at);
  const end = snapshot.finished_at ? Date.parse(snapshot.finished_at) : now;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "00:00:00";
  const elapsedSeconds = Math.floor((end - start) / 1000);
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;
  return [hours, minutes, seconds].map(value => String(value).padStart(2, "0")).join(":");
}

function ppuState(sites: SiteRuntime[]): SiteRunState | "partial" {
  if (!sites.length) return "ready";
  if (sites.some(site => site.state === "running")) return "running";
  if (sites.some(site => site.state === "error")) return "error";
  if (sites.some(site => site.state === "faulted")) return "faulted";
  if (sites.every(site => site.state === "success")) return "success";
  if (sites.every(site => site.state === "cancelled")) return "cancelled";
  if (sites.every(site => site.state === "stopped")) return "stopped";
  if (sites.every(site => site.state === "ready")) return "ready";
  return "partial";
}

export default function FactoryConsoleV2() {
  const { locale, t } = useI18n();
  const text = copy[locale];
  const {
    hydrated: workspaceHydrated,
    apiBase,
    engineeringSessionId: sessionId,
    ensureEngineeringSession,
    programmingImage: imageAsset,
    setProgrammingImage: setImageAsset,
    pmodDraftSelection: draftSelection,
    setPmodDraftSelection: setDraftSelection,
    pmodProductionSet: productionSet,
    setPmodProductionSet: setProductionSet,
    pmodBatchSelection: batchSelection,
    setPmodBatchSelection: setBatchSelection,
    pmodOperations: selectedOperations,
    setPmodOperations: setSelectedOperations,
    pmodSelectorCollapsed: selectorCollapsed,
    setPmodSelectorCollapsed: setSelectorCollapsed,
  } = useWorkspaceSession();

  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<Record<string, PPURuntime>>({});
  const [targetDevice, setTargetDevice] = useState<DeviceSearchResult | null>(null);
  const [operatorWarning, setOperatorWarning] = useState<string | null>(null);
  const [batchCommandState, setBatchCommandState] = useState<BatchCommandState>("idle");
  const [batchObservationState, setBatchObservationState] = useState<BatchObservationState>("connected");
  const [batchSnapshot, setBatchSnapshot] = useState<ServerBatchSnapshot | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const [repeatCount, setRepeatCount] = useState("1");
  const [siteRetryLimit, setSiteRetryLimit] = useState("3");
  const [failedSiteThreshold, setFailedSiteThreshold] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const imageInputRef = useRef<HTMLInputElement>(null);
  const logSequence = useRef(0);
  const activityReleaseRef = useRef<(() => void) | null>(null);
  const pollGenerationRef = useRef(0);
  const terminalBatchRef = useRef<string | null>(null);
  const initialProductionSet = useRef(productionSet);
  const initialBatchSelection = useRef(batchSelection);

  const appendLog = useCallback((message: string, level: LogEntry["level"] = "INFO") => {
    setLogs(current => [...current, {
      id: ++logSequence.current,
      time: nowTime(),
      level,
      text: message,
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

  const finalizeBatch = useCallback((snapshot: ServerBatchSnapshot) => {
    if (!terminalServerBatchStates.has(snapshot.state)) return;
    clearStoredBatch();
    endActivity();
    setBatchObservationState("connected");
    if (terminalBatchRef.current === snapshot.batch_id) return;
    terminalBatchRef.current = snapshot.batch_id;
    pollGenerationRef.current += 1;
    appendLog(`[BAT] TERMINAL · ${snapshot.state.toUpperCase()} · PASS ${snapshot.sites.reduce((total, site) => total + Math.max(0, site.completed_rounds), 0)} · FAIL ${snapshot.sites.reduce((total, site) => total + Math.max(0, site.final_failures), 0)} · ERROR ${snapshot.site_counts.error ?? 0} · CANCELLED ${snapshot.site_counts.cancelled ?? 0}`,
      snapshot.state === "error" ? "ERROR" : snapshot.state === "cancelled" || snapshot.state === "partial" ? "WARN" : "INFO");
  }, [appendLog, endActivity]);

  const applyBatchSnapshot = useCallback((next: ServerBatchSnapshot, sourceCatalog: EngineeringTargetCatalog) => {
    setBatchSnapshot(next);
    if (terminalServerBatchStates.has(next.state)) finalizeBatch(next);
    const snapshotMembership = selectionFromBatch(next);
    // Server Batch Runtime is execution truth. It must not rewrite operator
    // Batch Selection. These fallbacks only reconstruct browser context when a
    // fresh tab reconnects to an already-active server Batch.
    setBatchSelection(current => selectionCounts(current).sites > 0 ? current : snapshotMembership);
    setProductionSet(current => selectionCounts(current).sites > 0 ? current : snapshotMembership);
    setDraftSelection(current => selectionCounts(current).sites > 0 ? current : snapshotMembership);

    setRuntimes(current => {
      const merged = { ...current };
      for (const facility of sourceCatalog.facilities) {
        for (const target of facility.ppus) {
          const batchSites = next.sites.filter(site => site.facility_id === facility.facility_id && site.ppu_id === target.ppu_id);
          if (!batchSites.length) continue;
          const key = targetKey(facility.facility_id, target.ppu_id);
          const previous = current[key];
          const previousById = new Map((previous?.sites ?? []).map(site => [site.id, site]));
          const batchById = new Map(batchSites.map(site => [site.site_id, site]));
          const previousIds = new Set((previous?.sites ?? []).map(site => site.id));
          const sites = (previous?.sites ?? []).map(site => {
            const batchSite = batchById.get(site.id);
            return batchSite ? runtimeFromBatchSite(batchSite, site) : site;
          });
          for (const batchSite of batchSites) {
            if (!previousIds.has(batchSite.site_id)) sites.push(runtimeFromBatchSite(batchSite, previousById.get(batchSite.site_id)));
          }
          merged[key] = {
            facilityId: facility.facility_id,
            target,
            loading: false,
            sites: sites.sort((left, right) => left.id - right.id),
          };
        }
      }
      return merged;
    });
  }, [finalizeBatch, setBatchSelection, setDraftSelection, setProductionSet]);

  const pollServerBatch = useCallback(async (batchId: string, sourceCatalog: EngineeringTargetCatalog, generation: number) => {
    let previousState: ServerBatchState | null = null;
    let consecutiveFailures = 0;
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      if (pollGenerationRef.current !== generation) return;
      let next: ServerBatchSnapshot;
      try {
        next = await getServerBatch(apiBase, batchId);
      } catch (error) {
        if (pollGenerationRef.current !== generation) return;
        consecutiveFailures += 1;
        setBatchObservationState("reconnecting");
        const detail = error instanceof Error ? error.message : "unknown error";
        appendLog(`[BAT] OBSERVATION ERROR · ${detail} · RECONNECTING ${consecutiveFailures}`, "WARN");
        await delay(Math.min(POLL_INTERVAL_MS * 2 ** Math.min(consecutiveFailures, 5), 5000));
        continue;
      }
      if (pollGenerationRef.current !== generation) return;
      if (consecutiveFailures > 0) {
        appendLog(`[BAT] OBSERVATION RESTORED · ${batchId}`);
        consecutiveFailures = 0;
      }
      setBatchObservationState("connected");
      applyBatchSnapshot(next, sourceCatalog);
      if (next.state !== previousState) {
        appendLog(`[BAT] ${next.state.toUpperCase()} · ${next.batch_id}`, next.state === "error" ? "ERROR" : next.state === "cancelled" || next.state === "stopping" ? "WARN" : "INFO");
        previousState = next.state;
      }
      if (terminalServerBatchStates.has(next.state)) {
        return;
      }
      await delay(POLL_INTERVAL_MS);
    }
    endActivity();
    appendLog(`[BAT] OBSERVATION TIMEOUT · ${batchId}`, "ERROR");
  }, [apiBase, appendLog, applyBatchSnapshot, endActivity]);

  const loadSelectionRuntimes = useCallback(async (sourceCatalog: EngineeringTargetCatalog, selection: SelectionMap) => {
    const targets = sourceCatalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = selection[facility.facility_id]?.[target.ppu_id] ?? [];
      return siteIds.length ? [{ facility, target, siteIds, key: targetKey(facility.facility_id, target.ppu_id) }] : [];
    }));
    if (!targets.length) {
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
          const selected = new Set(item.siteIds);
          next[item.key] = {
            facilityId: item.facility.facility_id,
            target: item.target,
            loading: false,
            sites: result.value.status.sites.filter(site => selected.has(site.site_id)).map(runtimeFromStatus),
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
            const restored = await getServerBatch(apiBase, stored.batchId);
            if (stopped) return;
            applyBatchSnapshot(restored, nextCatalog);
            if (!terminalServerBatchStates.has(restored.state)) {
              beginActivity();
              const generation = ++pollGenerationRef.current;
              appendLog(`[BAT] RESTORED · ${restored.batch_id} · ${restored.state.toUpperCase()}`);
              void pollServerBatch(restored.batch_id, nextCatalog, generation).catch(error => {
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

        const restoredSet = normalizeSelection(cloneSelection(initialProductionSet.current));
        if (selectionCounts(restoredSet).sites > 0) {
          await loadSelectionRuntimes(nextCatalog, restoredSet);
          if (selectionCounts(initialBatchSelection.current).sites === 0) setBatchSelection(restoredSet);
          appendLog(`[SET] RESTORED · ${selectionCounts(restoredSet).ppus} PPUs · ${selectionCounts(restoredSet).sites} Sites`);
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
  }, [apiBase, appendLog, applyBatchSnapshot, beginActivity, endActivity, ensureEngineeringSession, loadSelectionRuntimes, pollServerBatch, setBatchSelection, workspaceHydrated]);

  const serverBatchState = batchSnapshot?.state ?? null;
  const serverBatchRunning = serverBatchState === "queued" || serverBatchState === "running" || serverBatchState === "stopping";
  const batchSubmitting = batchCommandState === "submitting";
  const batchAborting = batchCommandState === "aborting";
  const batchRunning = serverBatchRunning || batchSubmitting || batchAborting;

  useEffect(() => {
    if (!serverBatchRunning || !batchSnapshot?.started_at) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [batchSnapshot?.batch_id, batchSnapshot?.started_at, serverBatchRunning]);

  const draftCounts = useMemo(() => selectionCounts(draftSelection), [draftSelection]);
  const productionSetCounts = useMemo(() => selectionCounts(productionSet), [productionSet]);
  const batchCounts = useMemo(() => selectionCounts(batchSelection), [batchSelection]);
  const serverBatchMembership = useMemo(
    () => batchSnapshot ? selectionFromBatch(batchSnapshot) : {},
    [batchSnapshot],
  );
  const displayedBatchSelection = serverBatchRunning ? serverBatchMembership : batchSelection;
  const displayedBatchCounts = useMemo(
    () => selectionCounts(displayedBatchSelection),
    [displayedBatchSelection],
  );

  const productionTargets = useMemo<ProductionTarget[]>(() => {
    if (!catalog) return [];
    return catalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = productionSet[facility.facility_id]?.[target.ppu_id] ?? [];
      return siteIds.length ? [{ key: targetKey(facility.facility_id, target.ppu_id), facility, target, siteIds }] : [];
    }));
  }, [catalog, productionSet]);

  const batchTargets = useMemo<ProductionTarget[]>(() => productionTargets.flatMap(active => {
    const allowed = new Set(active.siteIds);
    const selected = (batchSelection[active.facility.facility_id]?.[active.target.ppu_id] ?? []).filter(siteId => allowed.has(siteId));
    return selected.length ? [{ ...active, siteIds: selected }] : [];
  }), [batchSelection, productionTargets]);

  const groupedProductionTargets = useMemo(() => {
    if (!catalog) return [];
    return catalog.facilities.map(facility => ({
      facility,
      targets: productionTargets.filter(active => active.facility.facility_id === facility.facility_id),
    })).filter(group => group.targets.length > 0);
  }, [catalog, productionTargets]);

  const manufacturing = useMemo(() => {
    if (!batchSnapshot) return { pass: 0, fail: 0, total: 0, yieldPercent: 0 };
    const pass = batchSnapshot.sites.reduce((total, site) => total + Math.max(0, site.completed_rounds), 0);
    const fail = batchSnapshot.sites.reduce((total, site) => total + Math.max(0, site.final_failures), 0);
    const total = pass + fail;
    return { pass, fail, total, yieldPercent: total > 0 ? pass / total * 100 : 0 };
  }, [batchSnapshot]);

  const repeatValue = parsePositiveInt(repeatCount);
  const retryValue = parseNonNegativeInt(siteRetryLimit);
  const thresholdValue = failedSiteThreshold === "" ? null : parsePositiveInt(failedSiteThreshold);
  const policyValid = repeatValue !== null && repeatValue <= 10_000
    && retryValue !== null && retryValue <= 20
    && (failedSiteThreshold === "" || (thresholdValue !== null && thresholdValue <= Math.max(1, batchCounts.sites)));
  const executionPolicy: BatchExecutionPolicy | null = policyValid ? {
    repeat_count: repeatValue!,
    site_retry_limit: retryValue!,
    failed_site_stop_threshold: thresholdValue,
  } : null;

  const allSitesExecutable = batchTargets.length > 0 && batchTargets.every(active => {
    const runtime = runtimes[active.key];
    if (!runtime || runtime.loading || runtime.error) return false;
    const byId = new Map(runtime.sites.map(site => [site.id, site]));
    return active.siteIds.every(siteId => {
      const site = byId.get(siteId);
      return Boolean(site?.enabled && site.state !== "running");
    });
  });
  const requiresImage = selectedOperations.some(operation => operation === "program" || operation === "verify");
  const syntheticMockImageAvailable = catalog?.provider === "mock";
  const batchReadiness = evaluateBatchReadiness({
    providerOnline: Boolean(catalog && !providerError),
    targetValid: syntheticMockImageAvailable || Boolean(targetDevice),
    selectedSiteCount: batchCounts.sites,
    selectedOperationCount: selectedOperations.length,
    requiresImage,
    imagePresent: Boolean(imageAsset) || syntheticMockImageAvailable,
    imageValid: !imageAsset || imageAsset.size <= MAX_IMAGE_BYTES,
    readSelected: selectedOperations.includes("read"),
    readParamsValid: true,
    allSitesExecutable,
    batchRunning: serverBatchState === "queued" || serverBatchState === "running" || batchSubmitting,
    batchCancelling: serverBatchState === "stopping" || batchAborting,
  });
  const batchStatusState = batchSubmitting
    ? "submitting"
    : batchAborting
      ? "aborting"
      : serverBatchRunning && batchObservationState === "reconnecting"
        ? "reconnecting"
        : serverBatchState ?? "idle";
  const batchStatusLabel = batchSubmitting
    ? "SUBMITTING"
    : batchAborting
      ? "ABORTING"
      : serverBatchRunning && batchObservationState === "reconnecting"
        ? "RECONNECTING"
      : serverBatchState
        ? serverBatchState.toUpperCase()
        : batchReadiness.label;

  const plannedIcCount = batchSnapshot
    ? batchSnapshot.sites.length * batchSnapshot.execution_policy.repeat_count
    : batchCounts.sites * (repeatValue ?? 0);

  const kpis = [
    { key: "production-sites", label: "SITES", value: productionSetCounts.sites },
    { key: "total-ic", label: "TOTAL IC", value: plannedIcCount },
    { key: "running", label: "RUNNING", value: batchSnapshot?.site_counts.running ?? 0 },
    { key: "pass", label: "PASS", value: manufacturing.pass, tone: "pass" as const },
    { key: "fail", label: "FAIL", value: manufacturing.fail, tone: "fail" as const },
    { key: "yield", label: "YIELD", value: `${manufacturing.yieldPercent.toFixed(1)}%`, tone: "info" as const },
    { key: "batch-time", label: "BATCH TIME", value: formatBatchTime(batchSnapshot, clockNow) },
  ];

  function productionTreeSiteIds(facilityId: string, ppuId: string): number[] {
    return draftSelection[facilityId]?.[ppuId] ?? [];
  }

  function setProductionPpuSites(facilityId: string, ppuId: string, siteIds: number[]) {
    if (batchRunning) return;
    setDraftSelection(current => normalizeSelection({
      ...current,
      [facilityId]: { ...(current[facilityId] ?? {}), [ppuId]: siteIds },
    }));
  }

  function toggleProductionFacility(facility: EngineeringFacilityTarget) {
    if (batchRunning) return;
    const selectedCount = facility.ppus.reduce((total, ppu) => total + productionTreeSiteIds(facility.facility_id, ppu.ppu_id).length, 0);
    const totalCount = facility.ppus.reduce((total, ppu) => total + ppu.site_count, 0);
    setDraftSelection(current => {
      const next = cloneSelection(current);
      if (selectedCount === totalCount && totalCount > 0) delete next[facility.facility_id];
      else next[facility.facility_id] = Object.fromEntries(facility.ppus.map(ppu => [ppu.ppu_id, allSiteIds(ppu)]));
      return normalizeSelection(next);
    });
  }

  function toggleProductionPpu(facilityId: string, ppu: EngineeringPPUTarget) {
    const current = productionTreeSiteIds(facilityId, ppu.ppu_id);
    setProductionPpuSites(facilityId, ppu.ppu_id, current.length === ppu.site_count ? [] : allSiteIds(ppu));
  }

  function toggleProductionSite(facilityId: string, ppu: EngineeringPPUTarget, siteId: number) {
    const current = productionTreeSiteIds(facilityId, ppu.ppu_id);
    setProductionPpuSites(facilityId, ppu.ppu_id, current.includes(siteId) ? current.filter(id => id !== siteId) : [...current, siteId]);
  }

  function selectEverything() {
    if (!catalog || batchRunning) return;
    setDraftSelection(Object.fromEntries(catalog.facilities.map(facility => [
      facility.facility_id,
      Object.fromEntries(facility.ppus.map(ppu => [ppu.ppu_id, allSiteIds(ppu)])),
    ])));
  }

  function clearEverything() {
    if (!batchRunning) setDraftSelection({});
  }

  async function applyProductionSet() {
    if (!catalog || !draftCounts.sites || batchRunning) return;
    const snapshot = normalizeSelection(cloneSelection(draftSelection));
    setProductionSet(snapshot);
    setBatchSelection(snapshot);
    setBatchCommandState("idle");
    setBatchSnapshot(null);
    setOperatorWarning(null);
    setClockNow(Date.now());
    clearStoredBatch();
    appendLog(`[SET] COMMIT · ${selectionCounts(snapshot).facilities} Facilities · ${selectionCounts(snapshot).ppus} PPUs · ${selectionCounts(snapshot).sites} Sites`);
    await loadSelectionRuntimes(catalog, snapshot);
  }

  function setBatchPpuSites(facilityId: string, ppuId: string, siteIds: number[]) {
    if (batchRunning) {
      setOperatorWarning(text.batchSelectionLocked);
      return;
    }
    const allowed = new Set(productionSet[facilityId]?.[ppuId] ?? []);
    const filtered = siteIds.filter(siteId => allowed.has(siteId));
    setBatchSelection(current => normalizeSelection({
      ...current,
      [facilityId]: { ...(current[facilityId] ?? {}), [ppuId]: filtered },
    }));
  }

  function toggleBatchPpu(active: ProductionTarget) {
    const current = batchSelection[active.facility.facility_id]?.[active.target.ppu_id] ?? [];
    setBatchPpuSites(active.facility.facility_id, active.target.ppu_id, current.length === active.siteIds.length ? [] : active.siteIds);
  }

  function toggleBatchSite(active: ProductionTarget, siteId: number) {
    const current = batchSelection[active.facility.facility_id]?.[active.target.ppu_id] ?? [];
    setBatchPpuSites(active.facility.facility_id, active.target.ppu_id, current.includes(siteId) ? current.filter(id => id !== siteId) : [...current, siteId]);
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedOperations(current => current.includes(operation) ? current.filter(item => item !== operation) : [...current, operation]);
  }

  async function executeBatch() {
    if (!catalog || batchRunning) return;
    if (!targetDevice && !syntheticMockImageAvailable) {
      setOperatorWarning(text.chooseTarget);
      return;
    }
    if (!batchCounts.sites) {
      setOperatorWarning(text.chooseBatchSite);
      return;
    }
    if (!selectedOperations.length) {
      setOperatorWarning(text.chooseOperation);
      return;
    }
    if (!batchReadiness.ready) {
      setOperatorWarning(batchReadiness.label);
      appendLog(`[BAT] BLOCKED · ${batchReadiness.label}`, "WARN");
      return;
    }
    if (!executionPolicy) {
      setOperatorWarning(text.policyInvalid);
      return;
    }
    const operations = operationOrder.filter(operation => selectedOperations.includes(operation));
    const targets = batchTargets.map(active => ({
      facility_id: active.facility.facility_id,
      ppu_id: active.target.ppu_id,
      site_ids: [...active.siteIds],
    }));
    if (!targets.length) return;

    setOperatorWarning(null);
    setClockNow(Date.now());
    terminalBatchRef.current = null;
    setBatchObservationState("connected");
    beginActivity();
    setBatchCommandState("submitting");
    appendLog(`[BAT] SUBMIT · ${batchCounts.ppus} PPUs · ${batchCounts.sites} Sites · ${operations.map(operation => operation.toUpperCase()).join(" → ")} · Target ${targetDevice ? targetDevice.icpn ?? targetDevice.identifier : "MOCK"}`);
    try {
      const accepted = await createServerBatch(apiBase, {
        sessionId,
        targets,
        operations,
        executionPolicy,
        targetDevice: targetDevice ? { vendor: targetDevice.vendor, identifier: targetDevice.identifier } : null,
        assetFile: imageAsset,
        allowSyntheticMockImage: syntheticMockImageAvailable,
        readOffset: 0,
        readLength: 256,
      });
      applyBatchSnapshot(accepted, catalog);
      setBatchCommandState("idle");
      if (terminalServerBatchStates.has(accepted.state)) return;
      writeStoredBatch(apiBase, accepted.batch_id);
      const generation = ++pollGenerationRef.current;
      appendLog(`[BAT] ACCEPTED · ${accepted.batch_id}`);
      void pollServerBatch(accepted.batch_id, catalog, generation).catch(error => {
        endActivity();
        appendLog(`[BAT] OBSERVATION ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
      });
    } catch (error) {
      endActivity();
      setBatchCommandState("idle");
      const detail = error instanceof Error ? error.message : "Batch submission failed";
      setOperatorWarning(detail);
      appendLog(`[BAT] SUBMISSION ERROR · ${detail}`, "ERROR");
    }
  }

  async function abortBatch() {
    const activeBatchId = batchSnapshot?.batch_id;
    if (!activeBatchId || !serverBatchRunning || serverBatchState === "stopping" || batchAborting) return;
    setBatchCommandState("aborting");
    appendLog(`[BAT] ABORT REQUESTED · ${activeBatchId}`, "WARN");
    try {
      const next = await cancelServerBatch(apiBase, activeBatchId);
      if (catalog) applyBatchSnapshot(next, catalog);
    } catch (error) {
      appendLog(`[BAT] ABORT ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
    } finally {
      setBatchCommandState("idle");
    }
  }

  function stateText(site: SiteRuntime): string {
    if (!site.enabled) return text.disabled;
    return text[site.state];
  }

  return (
    <main className="factoryConsoleV2">
      <section className="factoryConsoleShell">
        <header className="factoryConsoleHeader">
          <h1>{text.title}</h1>
          <div className={`factoryProvider ${providerError ? "offline" : catalog ? "online" : "loading"}`}>
            <i /><span>{providerError ? "OFFLINE" : catalog ? "Connected" : "Connecting"}</span><b>PMode</b>
          </div>
        </header>

        {!catalog && (
          <section className="factoryConsoleNotice" role="status">
            <b>{providerError ? text.offline : text.loading}</b>
            {providerError && <span>{providerError}</span>}
          </section>
        )}

        {catalog && (
          <>
            <OperatorKpiStrip items={kpis} ariaLabel="Production KPI" />

            <OperatorPanel
              number={1}
              title={text.productionSelection}
              className={`productionSiteSelection ${selectorCollapsed ? "is-collapsed" : ""}`}
              meta={`${text.productionSet}: ${productionSetCounts.sites} Sites / ${productionSetCounts.ppus} PPUs`}
              actions={(
                <button
                  type="button"
                  className="selectionVisibilityButton"
                  aria-expanded={!selectorCollapsed}
                  onClick={() => setSelectorCollapsed(current => !current)}
                >
                  {selectorCollapsed ? text.showSelection : text.hideSelection} {selectorCollapsed ? "⌄" : "⌃"}
                </button>
              )}
            >
              <p className="selectionHint">{text.productionSelectionHint}</p>
              <div className="productionTreeToolbar">
                <div>
                  <button type="button" onClick={selectEverything} disabled={batchRunning}>{text.selectAll}</button>
                  <button type="button" onClick={clearEverything} disabled={batchRunning || !draftCounts.sites}>{text.clearAll}</button>
                  <button type="button" className="commitProductionSet" onClick={() => void applyProductionSet()} disabled={batchRunning || !draftCounts.sites}>{text.applySet}</button>
                </div>
                <span>Draft · {draftCounts.facilities} F / {draftCounts.ppus} P / {draftCounts.sites} S</span>
              </div>
              <div className="productionTree" aria-label="Production Site Selection tree">
                {catalog.facilities.map((facility, facilityIndex) => {
                  const selectedCount = facility.ppus.reduce((total, ppu) => total + productionTreeSiteIds(facility.facility_id, ppu.ppu_id).length, 0);
                  const totalCount = facility.ppus.reduce((total, ppu) => total + ppu.site_count, 0);
                  const facilityChecked = totalCount > 0 && selectedCount === totalCount;
                  const facilityPartial = selectedCount > 0 && selectedCount < totalCount;
                  return (
                    <details className="productionTreeFacility" defaultOpen={facilityIndex === 0} key={facility.facility_id}>
                      <summary>
                        <input
                          type="checkbox"
                          checked={facilityChecked}
                          disabled={batchRunning}
                          ref={element => { if (element) element.indeterminate = facilityPartial; }}
                          onClick={event => event.stopPropagation()}
                          onChange={() => toggleProductionFacility(facility)}
                        />
                        <b>{facility.display_name}</b><small>{selectedCount}/{totalCount} Sites</small>
                      </summary>
                      <div className="productionTreePpus">
                        {facility.ppus.map((ppu, ppuIndex) => {
                          const siteIds = productionTreeSiteIds(facility.facility_id, ppu.ppu_id);
                          const ppuChecked = ppu.site_count > 0 && siteIds.length === ppu.site_count;
                          const ppuPartial = siteIds.length > 0 && siteIds.length < ppu.site_count;
                          return (
                            <details className="productionTreePpu" defaultOpen={facilityIndex === 0 && ppuIndex < 2} key={ppu.ppu_id}>
                              <summary>
                                <input
                                  type="checkbox"
                                  checked={ppuChecked}
                                  disabled={batchRunning}
                                  ref={element => { if (element) element.indeterminate = ppuPartial; }}
                                  onClick={event => event.stopPropagation()}
                                  onChange={() => toggleProductionPpu(facility.facility_id, ppu)}
                                />
                                <b>{ppu.display_name}</b><small>{siteIds.length}/{ppu.site_count} Sites</small>
                              </summary>
                              <div className="productionTreeSites">
                                {allSiteIds(ppu).map(siteId => {
                                  const checked = siteIds.includes(siteId);
                                  return (
                                    <label className={checked ? "selected" : ""} key={siteId}>
                                      <input
                                        type="checkbox"
                                        aria-label={`Production Set ${facility.facility_id} ${ppu.ppu_id} ${siteLabel(siteId)}`}
                                        checked={checked}
                                        disabled={batchRunning}
                                        onChange={() => toggleProductionSite(facility.facility_id, ppu, siteId)}
                                      />
                                      <span>{siteLabel(siteId)}</span>
                                    </label>
                                  );
                                })}
                              </div>
                            </details>
                          );
                        })}
                      </div>
                    </details>
                  );
                })}
              </div>
            </OperatorPanel>

            <OperatorPanel number={2} title={text.programmingJob} className="factoryProgrammingJob">
              <div className="factoryJobGrid">
                <label className="factoryField targetField">
                  <strong>1. {text.targetIc}</strong>
                  <ICPickerField apiBase={apiBase} value={targetDevice} onChange={setTargetDevice} disabled={batchRunning} />
                </label>

                <label className="factoryField imageFieldV2">
                  <strong>2. {text.image}</strong>
                  <div className="factoryImageControl">
                    <span title={imageAsset?.name}>{imageAsset?.name ?? (requiresImage && syntheticMockImageAvailable ? "Mock Synthetic Image" : "Select programming image (.bin)…")}</span>
                    <button type="button" disabled={batchRunning} onClick={() => imageInputRef.current?.click()}>{text.browse}</button>
                    <input
                      ref={imageInputRef}
                      type="file"
                      aria-label="Production Programming Image file"
                      accept=".bin,application/octet-stream"
                      hidden
                      disabled={batchRunning}
                      onChange={event => {
                        const file = event.target.files?.[0] ?? null;
                        if (file && file.size > MAX_IMAGE_BYTES) {
                          setOperatorWarning(text.imageTooLarge);
                          setImageAsset(null);
                          event.currentTarget.value = "";
                          return;
                        }
                        setImageAsset(file);
                        if (file) appendLog(`[IMG] SELECTED · ${file.name} · ${file.size} bytes`);
                      }}
                    />
                  </div>
                  <small>{text.imageHint}</small>
                </label>

                <div className="factoryField operationField">
                  <strong>3. {text.operations}</strong>
                  <div className="factoryOperationChecks">
                    {operationOrder.map(operation => (
                      <label key={operation}>
                        <input type="checkbox" checked={selectedOperations.includes(operation)} disabled={batchRunning} onChange={() => toggleOperation(operation)} />
                        <b>{operationCodes[operation]}</b> {t(`operation.${operation}`)}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="factoryField policyField">
                  <strong>4. {text.batchPolicy}</strong>
                  <div className="factoryPolicyControls">
                    <label>{text.repeat}<input aria-label="Repeat Count" type="number" min="1" max="10000" value={repeatCount} disabled={batchRunning} onChange={event => setRepeatCount(event.target.value)} /></label>
                    <label>{text.retry}<input aria-label="Site Retry Limit" type="number" min="0" max="20" value={siteRetryLimit} disabled={batchRunning} onChange={event => setSiteRetryLimit(event.target.value)} /></label>
                    <label>{text.stopPolicy}
                      <select aria-label="Stop Policy" value={failedSiteThreshold} disabled={batchRunning || !batchCounts.sites} onChange={event => setFailedSiteThreshold(event.target.value)}>
                        <option value="">{text.never}</option>
                        {Array.from({ length: batchCounts.sites }, (_, index) => index + 1).map(value => <option value={String(value)} key={value}>{value} Fail</option>)}
                      </select>
                    </label>
                  </div>
                </div>
              </div>

              <div className="factoryActionBar">
                <button type="button" className="factoryStartButton" onClick={() => void executeBatch()} disabled={!batchReadiness.ready || !policyValid}>▶ {text.start}</button>
                <div className={`factoryBatchStatus state-${batchStatusState}`} role="status" aria-label={text.batchStatus}>
                  <small>{text.batchStatus}</small>
                  <b>{batchStatusLabel}</b>
                </div>
                <button type="button" className="factoryAbortButton" onClick={() => void abortBatch()} disabled={!serverBatchRunning || serverBatchState === "stopping" || batchAborting}>■ {text.abort}</button>
              </div>
            </OperatorPanel>

            {operatorWarning && <div className="factoryWarning" role="alert"><span>{operatorWarning}</span><button type="button" onClick={() => setOperatorWarning(null)}>×</button></div>}

            <OperatorPanel
              number={3}
              title={text.liveStatus}
              className={`factoryLiveStatus density-${densityFor(productionSetCounts.sites)}`}
              meta={`${text.liveHint} · Selected ${displayedBatchCounts.sites}/${productionSetCounts.sites}`}
            >
              <div className="factoryLegend" aria-label="Site status legend">
                <span><i data-state="ready" /> READY</span>
                <span><i data-state="running" /> RUNNING</span>
                <span><i data-state="success" /> PASS</span>
                <span><i data-state="faulted" /> FAIL</span>
                <span><i data-state="error" /> ERROR</span>
                <span><i data-state="cancelled" /> CANCELLED</span>
                <span><i data-state="disabled" /> DISABLED</span>
              </div>

              {!productionSetCounts.sites ? <div className="factoryEmptySet">{text.noProductionSet}</div> : (
                <div className="factoryFacilityStack">
                  {groupedProductionTargets.map(group => (
                    <section className="factoryFacilityGroup" key={group.facility.facility_id} data-production-facility={group.facility.facility_id}>
                      <header><b>{group.facility.display_name}</b><span>{group.targets.length} PPUs</span></header>
                      <div className="factoryPpuRows">
                        {group.targets.map(active => {
                          const runtime = runtimes[active.key];
                          const selectedSiteIds = displayedBatchSelection[active.facility.facility_id]?.[active.target.ppu_id] ?? [];
                          const selectedSet = new Set(selectedSiteIds);
                          const allSelected = active.siteIds.length > 0 && selectedSiteIds.length === active.siteIds.length;
                          const partialSelected = selectedSiteIds.length > 0 && selectedSiteIds.length < active.siteIds.length;
                          const state = runtime ? ppuState(runtime.sites) : "ready";
                          return (
                            <section className={`factoryPpuRow state-${state}`} key={active.key} data-production-ppu={active.target.ppu_id}>
                              <header className="factoryPpuRowHeader">
                                <input
                                  type="checkbox"
                                  aria-label={`Batch select ${active.target.display_name}`}
                                  checked={allSelected}
                                  disabled={batchRunning}
                                  ref={element => { if (element) element.indeterminate = partialSelected; }}
                                  onChange={() => toggleBatchPpu(active)}
                                />
                                <div><b>{active.target.display_name}</b><small>{selectedSiteIds.length}/{active.siteIds.length} Sites selected</small></div>
                              </header>
                              {runtime?.loading && <div className="factoryPpuMessage">Loading…</div>}
                              {runtime?.error && <div className="factoryPpuMessage error">{runtime.error}</div>}
                              <div className="factorySiteLedGrid">
                                {(runtime?.sites ?? active.siteIds.map(id => ({ id, enabled: true, state: "ready", progress: 0, currentRound: 0, completedRounds: 0, attempts: 0, retries: 0, finalFailures: 0 } satisfies SiteRuntime))).map(site => {
                                  const selected = selectedSet.has(site.id);
                                  const displayState = site.enabled ? site.state : "disabled";
                                  return (
                                    <article
                                      className={`factorySiteLedCard state-${displayState} ${selected ? "batch-selected" : "batch-excluded"}`}
                                      data-production-site={site.id}
                                      data-site-state={displayState}
                                      data-batch-selected={selected ? "true" : "false"}
                                      aria-label={`${active.target.display_name} ${siteLabel(site.id)} ${stateText(site)}${site.currentRound ? ` IC ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}` : ""} ${selected ? "selected for Batch" : "excluded from Batch"}`}
                                      title={`${group.facility.display_name} / ${active.target.display_name} / ${siteLabel(site.id)} · ${stateText(site)}${site.currentRound ? ` · IC ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}` : ""}${site.operation ? ` · ${operationCodes[site.operation]} ${site.progress}%` : ""}`}
                                      key={site.id}
                                    >
                                      <div className="factorySiteLedCardTop">
                                        <input
                                          type="checkbox"
                                          aria-label={`Batch select ${active.target.display_name} ${siteLabel(site.id)}`}
                                          checked={selected}
                                          disabled={batchRunning || !site.enabled}
                                          onChange={() => toggleBatchSite(active, site.id)}
                                        />
                                        <b>{siteLabel(site.id)}</b>
                                      </div>
                                      <div className="factorySiteLed" data-state={displayState}><i /></div>
                                      <small>{displayState === "running" && site.currentRound ? `IC ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}` : stateText(site)}</small>
                                    </article>
                                  );
                                })}
                              </div>
                            </section>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </OperatorPanel>

            {batchSnapshot && batchSnapshot.error?.message && <div className="factoryRuntimeError">{batchSnapshot.error.error_code ? `${batchSnapshot.error.error_code} · ` : ""}{batchSnapshot.error.message}</div>}

            <ProductionLogPanel logs={logs} title={text.factoryLog} clearLabel={text.clearLog} onClear={() => setLogs([])} />
          </>
        )}
      </section>
    </main>
  );
}
