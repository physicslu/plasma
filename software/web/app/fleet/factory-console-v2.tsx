"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BatchReadinessCode } from "../batch-readiness";
import { beginBatchExecutionActivity, notifyBatchExecutionActivityChanged } from "../batch-execution-activity";
import type { DeviceSearchResult } from "../device-catalog-api";
import { useI18n } from "../i18n";
import { BatchSummary } from "../operator-ui/batch-summary";
import { ProgrammingJobPanel } from "../operator-ui/programming-job-panel";
import { OperatorPanel } from "../operator-ui/operator-panel";
import type {
  EngineeringFacilityTarget,
  EngineeringPPUTarget,
  EngineeringTargetCatalog,
  Operation,
  PPUStatus,
  SiteSnapshot,
} from "../plasma-api";
import { programmingRunLogLines } from "../programming/programming-run-log";
import {
  safeOffLabel,
  batchStatistics, cycleHistoryLogLines, snapshotStatistics, statisticsKpis, statisticsLogLine,
  statisticsMeta, type BatchStatistics,
} from "../programming/batch-statistics";
import { PROGRAMMING_SOURCE_ACCEPT } from "../operator-ui/programming-source-selector";
import {
  continueMarkKey, sitesToContinue,
  loadManagedTopology, loadProgrammingRoutes,
  ManagedProgrammingBlocked, ManagedStartOutcomeUnknown,
  PROGRAMMING_OPERATION_LABELS, attemptVerdict, batchSiteVerdict, routeDeclaring, routeSequenceOperations,
  loadUnitRun, managedCycleHistory, runManagedBatch, runOfUnit, unitCycleLabel,
  type ManagedTopology, type ProgrammingSource, type RoutesState,
} from "../programming/managed-programming";
import { getProgrammingBatch, getStartReconciliation, normalizeOperations,
  continueProgrammingBatch, operationsTakeImage, stopProgrammingBatch,
  type ProgrammingBatch, type ProgrammingRun, type SequenceOperation,
} from "../engineering/bundle-programming-api";
import { terminalServerBatchStates } from "../batch-snapshot";
import type {
  BatchSiteSnapshot,
  ServerBatchSiteState,
  ServerBatchSnapshot,
} from "../batch-snapshot";
import { useJobSetting, useWorkspaceSession, type SelectionMap } from "../workspace-session";
import {
  gatewayHealthFromError,
  summarizePPUHealth,
  type GatewayHealthState,
} from "./communication-health";
import { isRecoverablePPUStatusError, ppuRetryDelayMs } from "./ppu-status-recovery";
import {
  managedBatchBlocker,
  managedFactoryCatalog,
  managedPpuStatus,
  MANAGED_PRODUCTION_MODE, managedProductionSnapshot,
} from "./managed-factory-backend";
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
  communicationState?: "connected" | "reconnecting" | "failed";
  communicationAttempt?: number;
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

const POLL_INTERVAL_MS = 250;
const POLL_LIMIT = 14_400;
const MANAGED_BATCH_STORAGE_KEY = "plasma-managed-production-batch-v1";
const MANAGED_START_STORAGE_KEY = "plasma-managed-production-start-v1";
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };

const copy = {
  "zh-TW": {
    title: "PMODE · FACTORY CONSOLE",
    provider: "Programming Provider",
    loading: "正在載入 Programming Provider…",
    offline: "Programming 功能目前不可用。PPU 與 Gateway 連線狀態獨立判定。",
    gatewayUnreachable: "Plasma Web REST Gateway 無法連線。",
    systemSetup: "SYSTEM SETUP & TARGETING",
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
    loadFailed: "PPU 狀態載入失敗",
    batchSelectionLocked: "Batch 執行中，PPU / Site membership 已鎖定；只能使用整批 ABORT。",
  },
  "en-US": {
    title: "PMODE · FACTORY CONSOLE",
    provider: "Programming Provider",
    loading: "Loading Programming Provider…",
    offline: "Programming is currently unavailable. PPU and Gateway connectivity are reported independently.",
    gatewayUnreachable: "Plasma Web REST Gateway is unreachable.",
    systemSetup: "SYSTEM SETUP & TARGETING",
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
    communicationState: site.communication_state,
    communicationAttempt: site.communication_attempt,
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

function readManagedBatch(): string | null {
  try { return window.sessionStorage.getItem(MANAGED_BATCH_STORAGE_KEY); } catch { return null; }
}
function writeManagedBatch(id: string): void {
  try {
    window.sessionStorage.setItem(MANAGED_BATCH_STORAGE_KEY, id);
    notifyBatchExecutionActivityChanged();
  } catch { /* optional */ }
}
function clearManagedBatch(): void {
  try {
    window.sessionStorage.removeItem(MANAGED_BATCH_STORAGE_KEY);
    notifyBatchExecutionActivityChanged();
  } catch { /* optional */ }
}
function readManagedStart(): string | null {
  try { return window.sessionStorage.getItem(MANAGED_START_STORAGE_KEY); } catch { return null; }
}
function writeManagedStart(id: string): void {
  try { window.sessionStorage.setItem(MANAGED_START_STORAGE_KEY, id); } catch { /* optional */ }
}
function clearManagedStart(): void {
  try { window.sessionStorage.removeItem(MANAGED_START_STORAGE_KEY); } catch { /* optional */ }
}

function formatBatchTime(snapshot: ServerBatchSnapshot | null, now: number): string {
  if (!snapshot) return "00:00:00";
  if (!snapshot.started_at) return snapshot.state === "queued" ? "00:00:00" : "UNKNOWN";
  const start = Date.parse(snapshot.started_at);
  if (terminalServerBatchStates.has(snapshot.state) && !snapshot.finished_at) return "UNKNOWN";
  const end = snapshot.finished_at ? Date.parse(snapshot.finished_at) : now;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "UNKNOWN";
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
  const { locale } = useI18n();
  const text = copy[locale];
  const {
    hydrated: workspaceHydrated,
    pmodDraftSelection: draftSelection,
    setPmodDraftSelection: setDraftSelection,
    pmodProductionSet: productionSet,
    setPmodProductionSet: setProductionSet,
    pmodBatchSelection: batchSelection,
    setPmodBatchSelection: setBatchSelection,
    pmodSelectorCollapsed: selectorCollapsed,
    setPmodSelectorCollapsed: setSelectorCollapsed,
  } = useWorkspaceSession();

  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [gatewayHealth, setGatewayHealth] = useState<GatewayHealthState>("connecting");
  const [runtimes, setRuntimes] = useState<Record<string, PPURuntime>>({});
  const [targetDevice, setTargetDevice] = useJobSetting<DeviceSearchResult | null>("pmode.targetDevice", null);
  const [operatorWarning, setOperatorWarning] = useState<string | null>(null);
  const [batchCommandState, setBatchCommandState] = useState<BatchCommandState>("idle");
  const [batchObservationState, setBatchObservationState] = useState<BatchObservationState>("connected");
  const [batchSnapshot, setBatchSnapshot] = useState<ServerBatchSnapshot | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const [repeatCount, setRepeatCount] = useJobSetting("pmode.repeatCount", "1");
  const [replaceIc, setReplaceIc] = useJobSetting("pmode.replaceIc", true);
  // Manual Repeat: Sites the operator marked "IC replaced", per pause.
  const [replacedMarks, setReplacedMarks] = useState<ReadonlySet<string>>(new Set());
  const [siteRetryLimit, setSiteRetryLimit] = useJobSetting("pmode.siteRetryLimit", "3");
  const [failedSiteThreshold, setFailedSiteThreshold] = useJobSetting("pmode.failedSiteThreshold", "");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [programmingJobCollapsed, setProgrammingJobCollapsed] = useState(false);

  // Formal Control Station: Manager Registry / Fleet / Programming Routes and
  // Manager programming runs.
  const [managedTopology, setManagedTopology] = useState<ManagedTopology | null>(null);
  const [managedRoutes, setManagedRoutes] = useState<RoutesState | null>(null);
  const [programmingSource, setProgrammingSource] = useJobSetting<ProgrammingSource>("pmode.source", "image");
  const [managedFile, setManagedFile] = useJobSetting<File | null>("pmode.file", null);
  const [managedOperations, setManagedOperations] = useJobSetting<SequenceOperation[]>("pmode.operations", ["erase", "program", "verify"]);
  const [managedStartHold, setManagedStartHold] = useState<string | null>(null);
  const [managedBatchRecoveryId, setManagedBatchRecoveryId] = useState<string | null>(null);
  // Factory Log is a read-only view of the Manager's per-Site Job/Receipt truth.
  const loggedRecords = useRef(new Map<string, string>());
  const managedStartLock = useRef(false);
  const managedContinueLock = useRef(false);

  const logSequence = useRef(0);
  const activityReleaseRef = useRef<(() => void) | null>(null);
  const pollGenerationRef = useRef(0);
  const runtimeRecoveryGenerationRef = useRef(0);
  const terminalBatchRef = useRef<string | null>(null);
  // Site run lines read from the Manager by run_id; the TERMINAL line waits for them.
  const unitLogsRef = useRef<Promise<unknown>>(Promise.resolve());
  // Cycle History reader of the observed Repeat Batch (Batch Statistics v1).
  const cycleHistoryRef = useRef<{
    batchId: string; settled: number; topology: ManagedTopology | null; sync: () => Promise<void>;
  } | null>(null);
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

  /**
   * Never treat a Batch-level HTTP result as a Site PASS.
   *
   * The Manager runs Sites in concurrent lanes while a Batch carries one
   * current_run, so each finished Site's run is read by its run_id and that
   * Site's lines are logged together once it is loaded.
   */
  const logManagedBatch = useCallback((batch: ProgrammingBatch, topology: ManagedTopology | null) => {
    for (const [alias, observation] of Object.entries(batch.time_sync ?? {})) {
      const key = `${batch.batch_id}:time-sync:${alias}`;
      if (loggedRecords.current.has(key)) continue;
      loggedRecords.current.set(key, observation.status);
      appendLog(`[TIME SYNC] PPU ${alias} · ${observation.status} · ${observation.service ?? "service unknown"}${
        observation.after_offset_ms == null ? "" : ` · offset ${observation.after_offset_ms} ms`}${
        observation.warning_code ? ` · ${observation.warning_code}` : ""} · ${observation.elapsed_ms} ms`,
        observation.status === "SYNCED" || observation.status === "CORRECTED" ? "INFO" : "WARN");
    }
    // Every settled Cycle of a Repeat Batch reaches the Factory Log from the
    // Manager's Cycle History by cursor - also Cycles that started and ended
    // between two polls, after a reconnect or after a reload (a new reader
    // rebuilds from the first record).
    if (batch.policy.repeat > 1) {
      let history = cycleHistoryRef.current;
      if (history?.batchId !== batch.batch_id) {
        const repeat = batch.policy.repeat;
        const reader = managedCycleHistory(batch.batch_id, record => {
          // The latest topology, not the one of the first poll (may be null).
          const ppu = cycleHistoryRef.current?.topology?.ppus.find(item => item.alias === record.ppu_alias);
          const label = `PPU ${record.ppu_alias} · PPU ID ${ppu?.ppuId ?? "unknown"} · ${siteLabel(record.site_id)}`;
          for (const line of cycleHistoryLogLines(record, repeat, label)) {
            appendLog(line.text, line.failed ? "WARN" : "INFO");
          }
        });
        history = { batchId: batch.batch_id, settled: -1, topology, sync: () => reader.sync() };
        cycleHistoryRef.current = history;
      }
      if (topology) history.topology = topology;
      const settled = batch.cycles?.settled ?? 0;
      if (settled !== history.settled || batch.outcome != null) {
        history.settled = settled;
        const read = history.sync().catch(() => appendLog(
          "[CYCLE HISTORY] not loaded from the Manager; the Manager keeps it", "WARN"));
        unitLogsRef.current = Promise.allSettled([unitLogsRef.current, read]);
      }
    }
    for (const unit of batch.units) {
      const last = unit.attempts[unit.attempts.length - 1] ?? null;
      const key = `${batch.batch_id}:${unit.ppu_alias}:${unit.site_id}`;
      const ppu = topology?.ppus.find(item => item.alias === unit.ppu_alias);
      const interfaceName = ppu?.sites.find(site => site.site_id === unit.site_id)?.interface ?? "unknown";
      const label = `PPU ${unit.ppu_alias} · PPU ID ${ppu?.ppuId ?? "unknown"} · ${siteLabel(unit.site_id)}`;
      // Site Lane waiting for the operator (Replace IC / FAIL review): once per pause.
      const cycle = unit.cycle;
      if (unit.outcome == null && cycle?.state === "AWAITING_CONTINUE") {
        const waitKey = `${key}:wait:${cycle.continue_seq}`;
        if (!loggedRecords.current.has(waitKey)) {
          loggedRecords.current.set(waitKey, "");
          appendLog(`[SITE] ${label} · ${unitCycleLabel(unit) ?? "AWAITING_CONTINUE"}`,
            cycle.wait_reason === "REPLACE_IC" ? "INFO" : "WARN");
        }
      }
      // Each finished attempt's run once (Run Outcome), keyed by its run: a
      // Repeat Cycle restarts at attempt 1. The Site line once, when settled.
      const runKey = last?.outcome != null ? `${key}:run:${last.run_id ?? `${last.cycle_index ?? 1}:${last.attempt}`}` : null;
      const siteKey = unit.outcome != null ? `${key}:site` : null;
      const logRun = runKey != null && !loggedRecords.current.has(runKey);
      const logSite = siteKey != null && !loggedRecords.current.has(siteKey);
      if (!logRun && !logSite) continue;
      const runSeen = runKey != null && !logRun;
      if (runKey) loggedRecords.current.set(runKey, "");
      if (siteKey) loggedRecords.current.set(siteKey, "");
      const logUnit = (latestRun: ProgrammingRun | null, loadFailed: boolean) => {
        const verdict = batchSiteVerdict(batch, unit, latestRun);
        // An open Site Lane (Repeat, Retry) is judged on its last run alone;
        // a settled one on the Site verdict. Neither relaxes the evidence.
        const evidence = unit.outcome == null ? attemptVerdict(batch, unit, latestRun) : verdict;
        let evidenceLogged = runSeen;
        if (logRun && latestRun?.outcome != null) {
          if (latestRun.outcome === "PASS" && evidence.verdict !== "PASS") {
            appendLog(`[EVIDENCE] MANAGER RUN PASS REJECTED · ${evidence.reason ?? "unverified receipt"} · ${label}`, "ERROR");
          } else if (unit.outcome != null || evidence.verdict !== "PASS" || batch.policy.repeat <= 1) {
            // These lines carry the Site interface [EVIDENCE] line already.
            // A verified PASS Cycle of a Repeat lane is logged by Cycle History.
            for (const line of programmingRunLogLines(latestRun, { executionInterface: interfaceName })) {
              appendLog(`${line} · ${label}`, evidence.verdict === "PASS" ? "INFO" : "ERROR");
            }
            evidenceLogged = true;
          }
        } else if (logRun && loadFailed) {
          appendLog(`[RUN] Run ${last?.run_id ?? "—"} · receipt not loaded from the Manager · ${label}`, "WARN");
        }
        if (!logSite) return;
        appendLog(`[SITE] ${label} · ${verdict.verdict} · Run ${last?.run_id ?? "—"} · Job ${last?.job_id ?? "—"} · SAFE_OFF ${safeOffLabel(last?.safe_off_state, last?.safe_off)}${verdict.reason ?? unit.reason ? " · " + (verdict.reason ?? unit.reason) : ""}`,
          verdict.verdict === "PASS" ? "INFO" : "WARN");
        if ((unit.outcome === "PASS" || unit.outcome === "FAIL") && !evidenceLogged) {
          appendLog(interfaceName === "mock"
            ? `[EVIDENCE] MOCK RESULT · Site interface mock · ${label} · never a hardware qualification`
            : `[EVIDENCE] Site interface: ${interfaceName} · ${label}`);
        }
      };
      const held = runOfUnit(batch, unit);
      if (held || !last?.run_id) {
        logUnit(held, false);
      } else {
        const loaded = loadUnitRun(batch, unit).then(run => logUnit(run, run == null), () => logUnit(null, true));
        unitLogsRef.current = Promise.allSettled([unitLogsRef.current, loaded]);
      }
    }
  }, [appendLog]);

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
    // Keep the Managed observation key so reload can read terminal timing.
    endActivity();
    setBatchObservationState("connected");
    if (terminalBatchRef.current === snapshot.batch_id) return;
    terminalBatchRef.current = snapshot.batch_id;
    pollGenerationRef.current += 1;
    const stats = snapshotStatistics({
      sites: snapshot.sites, repeat: snapshot.execution_policy.repeat_count,
      replaceIc: snapshot.execution_policy.replace_ic_before_next_cycle !== false,
    });
    const terminal = `[BAT] TERMINAL · ${snapshot.state.toUpperCase()} · PASS ${stats.passCycles} · FAIL ${stats.failCycles} · ERROR ${snapshot.site_counts.error ?? 0} · CANCELLED ${snapshot.site_counts.cancelled ?? 0} · STOPPED ${snapshot.site_counts.stopped ?? 0} · Job Attempts ${stats.jobAttempts ?? "—"} · Retry ${stats.retryAttempts ?? "—"}`;
    const level = snapshot.state === "error" ? "ERROR" : snapshot.state === "cancelled" || snapshot.state === "partial" ? "WARN" : "INFO";
    // The terminal snapshot is applied just before its Site lines are logged in
    // the same handler; wait (one microtask, then any run_id reads) so the
    // TERMINAL line follows every Site's run lines.
    void Promise.resolve().then(() => unitLogsRef.current).then(() => {
      appendLog(terminal, level);
      appendLog(statisticsLogLine(stats), level);
    });
  }, [appendLog, endActivity]);

  const applyBatchSnapshot = useCallback((next: ServerBatchSnapshot, sourceCatalog: EngineeringTargetCatalog) => {
    setBatchSnapshot(next);
    if (terminalServerBatchStates.has(next.state)) finalizeBatch(next);
    const snapshotMembership = selectionFromBatch(next);
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

  /** Reload-safe read-only observer of an accepted Manager-owned Batch. */
  const pollManagedBatch = useCallback(async (
    batchId: string, sourceCatalog: EngineeringTargetCatalog, generation: number, topology: ManagedTopology,
  ) => {
    let failures = 0;
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      if (pollGenerationRef.current !== generation) return;
      try {
        const current = await getProgrammingBatch(batchId);
        if (pollGenerationRef.current !== generation) return;
        const heldStart = readManagedStart();
        if (current.batch_id !== batchId || (heldStart && current.start_id !== heldStart)) {
          throw new Error("Manager Batch/Start identity mismatch");
        }
        failures = 0;
        setBatchObservationState("connected");
        setGatewayHealth("online");
        const snapshot = managedProductionSnapshot(current, topology);
        // Persist UNKNOWN/falsely reported PASS *before* a terminal snapshot
        // clears the ordinary active Batch ID. Reload must never unlock it.
        if (current.outcome == null || current.outcome === "OUTCOME_UNKNOWN"
            || current.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
            || (current.outcome === "PASS" && snapshot.state !== "success")) {
          if (/^[0-9a-f]{32}$/.test(current.start_id)) {
            writeManagedStart(current.start_id);
            setManagedStartHold(current.start_id);
          }
        }
        if (current.outcome != null && current.outcome !== "OUTCOME_UNKNOWN" && !current.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
            && !(current.outcome === "PASS" && snapshot.state !== "success")) {
          clearManagedStart();
          setManagedStartHold(null);
        }
        applyBatchSnapshot(snapshot, sourceCatalog);
        logManagedBatch(current, topology);
        if (current.outcome != null) return;
      } catch (reason) {
        failures += 1;
        if (pollGenerationRef.current !== generation) return;
        setBatchObservationState("reconnecting");
        appendLog(`[BAT] MANAGER JOURNAL UNAVAILABLE · ${batchId} · ${reason instanceof Error ? reason.message : "unknown"} · no resubmission`, "WARN");
        await delay(Math.min(POLL_INTERVAL_MS * 2 ** Math.min(failures, 5), 5000));
        continue;
      }
      await delay(POLL_INTERVAL_MS);
    }
    appendLog(`[BAT] MANAGER OBSERVATION EXHAUSTED · ${batchId}; still held for read-only recovery`, "ERROR");
  }, [appendLog, applyBatchSnapshot, logManagedBatch]);

  const loadSelectionRuntimes = useCallback(async (sourceCatalog: EngineeringTargetCatalog, selection: SelectionMap) => {
    const generation = ++runtimeRecoveryGenerationRef.current;
    const targets = sourceCatalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = selection[facility.facility_id]?.[target.ppu_id] ?? [];
      return siteIds.length ? [{ facility, target, siteIds, key: targetKey(facility.facility_id, target.ppu_id) }] : [];
    }));
    if (!targets.length) {
      setRuntimes({});
      return;
    }

    // Site status is the Manager Fleet observation of that Alias.
    const readStatus = async (alias: string) => managedPpuStatus(await loadManagedTopology(), alias);

    const runtimeForStatus = (item: (typeof targets)[number], status: PPUStatus): PPURuntime => {
      const selected = new Set(item.siteIds);
      return {
        facilityId: item.facility.facility_id,
        target: item.target,
        loading: false,
        sites: status.sites.filter(site => selected.has(site.site_id)).map(runtimeFromStatus),
      };
    };

    const recoverTarget = async (item: (typeof targets)[number], failureCount: number): Promise<void> => {
      await delay(ppuRetryDelayMs(failureCount));
      if (runtimeRecoveryGenerationRef.current !== generation) return;
      try {
        const status = await readStatus(item.target.ppu_id);
        if (runtimeRecoveryGenerationRef.current !== generation) return;
        setGatewayHealth("online");
        setRuntimes(current => ({ ...current, [item.key]: runtimeForStatus(item, status) }));
        appendLog(`[PPU] STATUS RESTORED · ${item.target.display_name}`);
      } catch (error) {
        if (runtimeRecoveryGenerationRef.current !== generation) return;
        setGatewayHealth("online");
        const detail = error instanceof Error ? error.message : text.loadFailed;
        setRuntimes(current => {
          const previous = current[item.key];
          if (!previous) return current;
          return { ...current, [item.key]: { ...previous, loading: false, error: detail } };
        });
        if (isRecoverablePPUStatusError(error)) void recoverTarget(item, failureCount + 1);
      }
    };

    setRuntimes(Object.fromEntries(targets.map(item => [item.key, {
      facilityId: item.facility.facility_id,
      target: item.target,
      sites: [],
      loading: true,
    } satisfies PPURuntime])));
    const results = await Promise.allSettled(targets.map(async item => (
      { item, status: await readStatus(item.target.ppu_id) }
    )));
    if (runtimeRecoveryGenerationRef.current !== generation) return;
    // The Manager answered; an unobservable PPU is a PPU fault, not a Gateway fault.
    setGatewayHealth("online");
    setRuntimes(current => {
      const next = { ...current };
      results.forEach((result, index) => {
        const item = targets[index];
        if (result.status === "fulfilled") {
          next[item.key] = runtimeForStatus(item, result.value.status);
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
    results.forEach((result, index) => {
      if (result.status !== "rejected" || !isRecoverablePPUStatusError(result.reason)) return;
      const item = targets[index];
      appendLog(`[PPU] STATUS ERROR · ${item.target.display_name} · RECONNECTING`, "WARN");
      void recoverTarget(item, 1);
    });
  }, [appendLog, text.loadFailed]);

  useEffect(() => {
    if (!workspaceHydrated) return;
    let stopped = false;
    void (async () => {
      await Promise.resolve();
      if (stopped) return;
      // Durable transaction safety does not depend on Fleet/Route availability.
      setManagedStartHold(readManagedStart());
      setManagedBatchRecoveryId(readManagedBatch());
      try {
        const restoredTopology = await loadManagedTopology();
        const routes = restoredTopology.ppus[0]
          ? await loadProgrammingRoutes(restoredTopology.ppus[0].alias)
          : { routes: [], error: null };
        if (stopped) return;
        setManagedTopology(restoredTopology);
        setManagedRoutes(routes);
        const nextCatalog: EngineeringTargetCatalog = managedFactoryCatalog(restoredTopology);
        setGatewayHealth("online");
        setCatalog(nextCatalog);
        setProviderError(null);
        appendLog(`[PROVIDER] ${nextCatalog.provider.toUpperCase()} · ${nextCatalog.facility_count} Facilities · ${nextCatalog.ppu_count} PPUs · ${nextCatalog.site_count} Sites`);

        // Managed mode observes the Manager Journal by immutable Batch ID.
        // A reload never restarts or resubmits a Batch or any Site Job.
        let managedId = readManagedBatch();
        const pendingStart = readManagedStart();
        if (pendingStart) setManagedStartHold(pendingStart);
        if (pendingStart && !managedId) {
          setManagedStartHold(pendingStart);
          try {
            const result = await getStartReconciliation(pendingStart);
            if (result.start_id !== pendingStart || result.kind !== "batch") {
              throw new Error("Manager answered for a different Start or transaction kind");
            }
            if (result.state === "NOT_ACCEPTED") {
              clearManagedStart();
              setManagedStartHold(null);
              appendLog(`[START] NOT ACCEPTED · ${pendingStart} · safe to unlock`);
            } else if (result.batch?.batch_id) {
              managedId = result.batch.batch_id;
              writeManagedBatch(managedId);
              // A Batch ID is an observation key, not proof of safe completion.
              // Keep the immutable Start until its journal is read successfully.
              writeManagedStart(pendingStart);
              setManagedStartHold(pendingStart);
            } else {
              setOperatorWarning(`Manager Start ${pendingStart} remains ${result.state}; no new Job may be submitted until reconciled.`);
            }
          } catch (reason) {
            setOperatorWarning(`Manager Start ${pendingStart} cannot be reconciled: ${reason instanceof Error ? reason.message : "unknown"}. No resubmission.`);
          }
        }
        if (managedId) {
          const storedBatchId = managedId;
          try {
            const managerTruth = await getProgrammingBatch(storedBatchId);
            const heldStart = readManagedStart();
            if (managerTruth.batch_id !== storedBatchId
                || (heldStart && managerTruth.start_id !== heldStart)) {
              throw new Error("Manager Batch/Start identity mismatch");
            }
            const restored = managedProductionSnapshot(managerTruth, restoredTopology);
            if (stopped) return;
            setGatewayHealth("online");
            // The stored Batch can become UNKNOWN while the Browser was gone.
            // Recreate its immutable Start hold before terminal cleanup.
            if (managerTruth.outcome == null || managerTruth.outcome === "OUTCOME_UNKNOWN"
                || managerTruth.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
                || (managerTruth.outcome === "PASS" && restored.state !== "success")) {
              if (/^[0-9a-f]{32}$/.test(managerTruth.start_id)) {
                writeManagedStart(managerTruth.start_id);
                setManagedStartHold(managerTruth.start_id);
              }
            }
            if (managerTruth.outcome != null && managerTruth.outcome !== "OUTCOME_UNKNOWN" && !managerTruth.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
                && !(managerTruth.outcome === "PASS" && restored.state !== "success")) {
              clearManagedStart();
              setManagedStartHold(null);
            }
            applyBatchSnapshot(restored, nextCatalog);
            setManagedBatchRecoveryId(null);
            logManagedBatch(managerTruth, restoredTopology);
            if (!terminalServerBatchStates.has(restored.state)) {
              beginActivity();
              const generation = ++pollGenerationRef.current;
              appendLog(`[BAT] RESTORED · ${restored.batch_id} · ${restored.state.toUpperCase()}`);
              void pollManagedBatch(restored.batch_id, nextCatalog, generation, restoredTopology).catch(error => {
                endActivity();
                appendLog(`[BAT] OBSERVATION ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
              });
              return;
            }
          } catch (error) {
            setGatewayHealth(gatewayHealthFromError(error));
            // Unknown Manager state is not grounds to clear a durable Batch ID.
            setOperatorWarning(`Manager Batch ${storedBatchId} cannot be read. Retained for read-only reconciliation; no resubmission.`);
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
        const detail = error instanceof Error ? error.message : "Programming provider unavailable";
        const nextGatewayHealth = gatewayHealthFromError(error);
        setGatewayHealth(nextGatewayHealth);
        setProviderError(detail);
        setCatalog(null);
        appendLog(`[PROGRAMMING] provider unavailable · ${detail}`, nextGatewayHealth === "online" ? "WARN" : "ERROR");
      }
    })();
    return () => {
      stopped = true;
      pollGenerationRef.current += 1;
      runtimeRecoveryGenerationRef.current += 1;
      endActivity();
    };
  }, [appendLog, applyBatchSnapshot, beginActivity, endActivity, loadSelectionRuntimes, logManagedBatch, pollManagedBatch, setBatchSelection, workspaceHydrated]);

  // Managed: keep the Fleet observation current so capability is never judged on a stale view.
  useEffect(() => {
    if (!catalog) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      void loadManagedTopology().then(next => { if (!stopped) setManagedTopology(next); }).catch(() => {});
    }, 5000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [catalog]);

  const serverBatchState = batchSnapshot?.state ?? null;
  const serverBatchRunning = serverBatchState === "queued" || serverBatchState === "running" || serverBatchState === "stopping";
  const batchSubmitting = batchCommandState === "submitting";
  const batchAborting = batchCommandState === "aborting";
  const batchRunning = serverBatchRunning || batchSubmitting || batchAborting;

  useEffect(() => {
    if (batchRunning) return;
    setBatchSelection(current => {
      const next: SelectionMap = {};
      for (const [facilityId, ppus] of Object.entries(current)) {
        for (const [ppuId, siteIds] of Object.entries(ppus)) {
          const runtime = runtimes[targetKey(facilityId, ppuId)];
          if (!runtime || runtime.loading || runtime.error) {
            if (siteIds.length > 0) {
              next[facilityId] ??= {};
              next[facilityId][ppuId] = [...siteIds];
            }
            continue;
          }
          const enabledSiteIds = new Set(runtime.sites.filter(site => site.enabled).map(site => site.id));
          const enabledSelection = siteIds.filter(siteId => enabledSiteIds.has(siteId));
          if (enabledSelection.length > 0) {
            next[facilityId] ??= {};
            next[facilityId][ppuId] = enabledSelection;
          }
        }
      }
      const normalizedCurrent = normalizeSelection(current);
      const normalizedNext = normalizeSelection(next);
      return JSON.stringify(normalizedCurrent) === JSON.stringify(normalizedNext) ? current : normalizedNext;
    });
  }, [batchRunning, batchSelection, runtimes, setBatchSelection]);

  useEffect(() => {
    if (!serverBatchRunning || !batchSnapshot?.started_at
        || !Number.isFinite(Date.parse(batchSnapshot.started_at)) || batchSnapshot.finished_at) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [batchSnapshot?.batch_id, batchSnapshot?.started_at, batchSnapshot?.finished_at, serverBatchRunning]);

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


  const repeatValue = parsePositiveInt(repeatCount);
  const waitingSites = batchSnapshot?.awaiting_continue ?? [];
  const continuingSites = sitesToContinue(
    waitingSites.map(site => ({ ...site, alias: site.ppu_id, siteId: site.site_id, continueSeq: site.continue_seq })),
    batchSnapshot?.sites.length ?? 0, replacedMarks);
  const retryValue = parseNonNegativeInt(siteRetryLimit);
  const thresholdValue = failedSiteThreshold === "" ? null : parsePositiveInt(failedSiteThreshold);
  const policyValid = repeatValue !== null && repeatValue <= 10_000
    && retryValue !== null && retryValue <= 5
    && (failedSiteThreshold === "" || (thresholdValue !== null && thresholdValue <= Math.max(1, batchCounts.sites)));

  const ppuHealth = useMemo(() => summarizePPUHealth(
    gatewayHealth,
    Boolean(catalog),
    Boolean(providerError),
    productionTargets.map(active => {
      const runtime = runtimes[active.key];
      const reconnecting = runtime?.sites.some(site => site.communicationState === "reconnecting") ?? false;
      const communicationFailed = runtime?.sites.some(site => site.communicationState === "failed") ?? false;
      return {
        loading: !runtime || runtime.loading || reconnecting,
        error: runtime?.error ?? (communicationFailed ? "PPU communication failed" : undefined),
        expectedSiteIds: active.siteIds,
        observedSiteIds: runtime?.sites.map(site => site.id) ?? [],
      };
    }),
  ), [catalog, gatewayHealth, productionTargets, providerError, runtimes]);
  const gatewayTone = gatewayHealth === "online" ? "online" : gatewayHealth === "unreachable" ? "offline" : "loading";
  const gatewayLabel = gatewayHealth === "online"
    ? "Gateway ONLINE"
    : gatewayHealth === "unreachable"
      ? "Gateway UNREACHABLE"
      : "Gateway CONNECTING";

  // Managed readiness: ONLINE and Programming capability are separate facts.
  const icpn = targetDevice?.icpn ?? targetDevice?.identifier ?? null;
  // Both modes use one ordered E / P / V Operations List (never flash_cycle).
  // Site presence/compatibility is separately certified by the PPU.
  const managedOperationOptions = routeSequenceOperations(managedRoutes?.routes ?? null, icpn, batchTargets[0]?.siteIds[0] ?? null);
  const managedChosen = normalizeOperations(managedOperations.filter(item => managedOperationOptions.includes(item)));
  const managedNeedsFile = managedChosen != null && operationsTakeImage(managedChosen);
  const managedRoute = managedChosen && batchTargets.length
    ? routeDeclaring(managedRoutes?.routes ?? null, icpn, batchTargets[0].siteIds[0], managedChosen)
    : null;
  const managedSourceLimit = programmingSource === "bundle" ? 1024 * 1024 + 256 * 1024 : 1024 * 1024;
  const managedReadiness = ((): { code: BatchReadinessCode; label: string; ready: boolean; reason: string } => {
    const blocked = (code: BatchReadinessCode, label: string, reason: string) => ({ code, label, ready: false, reason });
    if (serverBatchState === "stopping" || batchAborting) return { code: "cancelling", label: "CANCELLING", ready: false, reason: "" };
    if (serverBatchState === "queued" || serverBatchState === "running" || batchSubmitting) {
      return { code: "running", label: "RUNNING", ready: false, reason: "" };
    }
    if (managedStartHold) {
      return blocked("programming-unavailable", "START RECONCILIATION REQUIRED",
        `Manager Start ${managedStartHold} is unresolved (OUTCOME_UNKNOWN). Inspect its journal before another Batch; nothing is resubmitted.`);
    }
    if (managedBatchRecoveryId) {
      return blocked("programming-unavailable", "BATCH OBSERVATION REQUIRED",
        `Manager Batch ${managedBatchRecoveryId} has not been read. Reload to observe its journal; no resubmission.`);
    }
    if (!catalog) return blocked("programming-unavailable", "MANAGER OFFLINE", providerError ?? "The Manager Registry is unavailable.");
    if (!icpn) return blocked("no-target", "NO TARGET", "Select a Target IC.");
    if (!batchCounts.sites) return blocked("no-site", "NO SITE", "Select at least one Site.");
    if (!managedRoutes?.routes) {
      return blocked("programming-unavailable", "ROUTES UNAVAILABLE", managedRoutes?.error ?? "Programming Routes are unavailable.");
    }
    const blocker = managedBatchBlocker(managedTopology, managedRoutes.routes, icpn,
      batchTargets.map(active => ({ alias: active.target.ppu_id, siteIds: active.siteIds })));
    if (blocker) return blocked("programming-unavailable", blocker.label, blocker.reason);
    if (!policyValid) return blocked("programming-unavailable", "POLICY INVALID", "Managed Repeat is 1; Retry must be 0–5; Stop threshold must be within the Target Set.");
    if (!managedChosen || !managedRoute) return blocked("no-op", "OPERATIONS INVALID",
      "Select a valid ordered E / P / V list (Erase + Verify without Program is unsupported) with one qualified Route.");
    if (managedNeedsFile && !managedFile) {
      return programmingSource === "bundle"
        ? blocked("image-required", "BUNDLE REQUIRED", "Select your canonical Bundle v3 (.zip).")
        : blocked("image-required", "IMAGE REQUIRED", "Select a Programming Image (.bin).");
    }
    if (managedNeedsFile && managedFile && (managedFile.size <= 0 || managedFile.size > managedSourceLimit)) {
      return blocked("image-invalid", "FILE INVALID", `The selected file must be 1 to ${managedSourceLimit} bytes.`);
    }
    // Ready for the restricted sequential mode only; never a generic production READY.
    return { code: "batch-ready", label: MANAGED_PRODUCTION_MODE.readyLabel, ready: true, reason: "" };
  })();
  const batchReadiness = managedReadiness;
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

  // Batch Statistics v1, shared with EMode. Same-IC Debug repeats one IC per
  // Site: its Cycles are never IC output, so it shows no YIELD.
  const statistics: BatchStatistics = batchSnapshot
    ? snapshotStatistics({
      sites: batchSnapshot.sites,
      repeat: batchSnapshot.execution_policy.repeat_count,
      replaceIc: batchSnapshot.execution_policy.replace_ic_before_next_cycle !== false,
    })
    : batchStatistics({ sites: batchCounts.sites, repeat: repeatValue ?? 0, replaceIc });
  const sameIcDebug = statistics.mode === "SAME_IC_DEBUG";
  const roundUnit = sameIcDebug ? "CYCLE" : "IC";
  const kpis = statisticsKpis(statistics, formatBatchTime(batchSnapshot, clockNow), "production-sites");

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
    clearManagedBatch();
    setOperatorWarning(null);
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

  function toggleBatchFacility(facilityId: string, targets: ProductionTarget[]) {
    if (batchRunning) {
      setOperatorWarning(text.batchSelectionLocked);
      return;
    }
    const totalSites = targets.reduce((total, active) => total + active.siteIds.length, 0);
    const selectedSites = targets.reduce(
      (total, active) => total + (batchSelection[facilityId]?.[active.target.ppu_id] ?? []).length,
      0,
    );
    setBatchSelection(current => {
      const next = cloneSelection(current);
      if (totalSites > 0 && selectedSites === totalSites) delete next[facilityId];
      else next[facilityId] = Object.fromEntries(targets.map(active => [active.target.ppu_id, [...active.siteIds]]));
      return normalizeSelection(next);
    });
  }

  function toggleBatchSite(active: ProductionTarget, siteId: number) {
    const current = batchSelection[active.facility.facility_id]?.[active.target.ppu_id] ?? [];
    setBatchPpuSites(active.facility.facility_id, active.target.ppu_id, current.includes(siteId) ? current.filter(id => id !== siteId) : [...current, siteId]);
  }

  // Managed: switching the Programming Source only clears local state.
  function changeProgrammingSource(next: ProgrammingSource) {
    if (batchRunning || next === programmingSource) return;
    setProgrammingSource(next);
    setManagedFile(null);
    setBatchSnapshot(null);
    clearManagedBatch();
    loggedRecords.current.clear();
    setOperatorWarning(null);
    appendLog(`[SOURCE] ${next.toUpperCase()} · previous file and results cleared`);
  }

  // PR-D: ONE canonical Manager-owned Batch across every selected PPU/Site.
  // The Browser never sequences Site Jobs and never automatically retries a lost Start.
  async function executeManagedBatch() {
    if (!catalog || batchRunning || managedStartLock.current) return;
    if (!managedReadiness.ready || !icpn || !managedChosen || !managedRoute || !batchTargets.length
        || (managedNeedsFile && !managedFile)) {
      setOperatorWarning(`${managedReadiness.label} · ${managedReadiness.reason}`);
      appendLog(`[BAT] BLOCKED · ${managedReadiness.label} · ${managedReadiness.reason}`, "WARN");
      return;
    }
    const targets = batchTargets.map(active => ({
      ppu_alias: active.target.ppu_id, site_ids: [...active.siteIds],
    }));
    const primary = targets[0];
    // The Route constrains the operation and erase range, not a physical Site.
    const request = managedNeedsFile && managedFile
      ? {
        alias: primary.ppu_alias, siteIds: primary.site_ids, targets,
        icpn, operations: managedChosen, source: programmingSource, file: managedFile,
        retryLimit: retryValue ?? 0, repeat: repeatValue ?? 1, replaceIc,
        stopPolicy: thresholdValue == null ? { kind: "never" as const }
          : { kind: "failed_sites" as const, threshold: thresholdValue },
      }
      : {
        alias: primary.ppu_alias, siteIds: primary.site_ids, targets,
        icpn, operations: ["erase"] as const, source: programmingSource, file: null,
        range: { address: managedRoute.flash_base, length: managedRoute.flash_size },
        retryLimit: retryValue ?? 0, repeat: repeatValue ?? 1, replaceIc,
        stopPolicy: thresholdValue == null ? { kind: "never" as const }
          : { kind: "failed_sites" as const, threshold: thresholdValue },
      };
    managedStartLock.current = true;
    setBatchCommandState("submitting");
    setOperatorWarning(null);
    terminalBatchRef.current = null;
    setBatchObservationState("connected");
    loggedRecords.current.clear();
    beginActivity();
    appendLog(`[BAT] START MANAGER · ${targets.length} PPUs · ${batchCounts.sites} Sites · ${managedChosen.join(" → ").toUpperCase()} · ${icpn} · Retry ${retryValue ?? 0} · Stop ${thresholdValue ?? "never"} · Repeat ${repeatValue ?? 1} Cycle(s)/Site · ${replaceIc ? "replace IC each Cycle" : "same-IC Debug"}`);
    try {
      await runManagedBatch(request, {
        onStartId: startId => {
          clearManagedBatch();
          writeManagedStart(startId);
          setManagedStartHold(startId);
          appendLog(`[START] Manager issued ${startId}; waiting for canonical Batch acceptance`);
        },
        onBatch: next => {
          setBatchCommandState("idle");
          setBatchObservationState("connected");
          // A confirmed Manager Batch ID is the durable observation key.
          writeManagedBatch(next.batch_id);
          const snapshot = managedProductionSnapshot(next, managedTopology);
          applyBatchSnapshot(snapshot, catalog);
          logManagedBatch(next, managedTopology);
          if (next.outcome == null || next.outcome === "OUTCOME_UNKNOWN" || next.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
              || (next.outcome === "PASS" && snapshot.state !== "success")) {
            // An unknown transaction or invalid PASS evidence requires a hold.
            // Do not silently release it on a terminal Batch or a page reload.
            writeManagedStart(next.start_id);
            setManagedStartHold(next.start_id);
          } else {
            clearManagedStart();
            setManagedStartHold(null);
          }
        },
        onPollError: message => {
          setBatchObservationState("reconnecting");
          appendLog(`[BAT] OBSERVATION UNAVAILABLE · ${message}`, "WARN");
        },
      });
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Manager Batch failed";
      if (reason instanceof ManagedProgrammingBlocked) {
        // Definitive 4xx refusal: Manager confirms no Batch was accepted.
        clearManagedStart();
        setManagedStartHold(null);
      }
      if (reason instanceof ManagedStartOutcomeUnknown) {
        // The Start may have been accepted. Keep its ID and block new Start.
        writeManagedStart(reason.planId);
        setManagedStartHold(reason.planId);
      }
      setOperatorWarning(detail);
      appendLog(`[BAT] ${reason instanceof ManagedStartOutcomeUnknown ? "START OUTCOME UNKNOWN" : "ERROR"} · ${detail}`, "ERROR");
      endActivity();
    } finally {
      managedStartLock.current = false;
      setBatchCommandState("idle");
    }
  }

  /** Operator-initiated read-only reconciliation of a lost Manager Start. */
  async function reconcileHeldManagerStart() {
    const held = managedStartHold ?? readManagedStart();
    if (!held || !catalog) return;
    try {
      const reconciled = await getStartReconciliation(held);
      if (reconciled.start_id !== held || reconciled.kind !== "batch") {
        throw new Error("Manager answered for a different Start or transaction kind");
      }
      if (reconciled.state === "NOT_ACCEPTED") {
        clearManagedStart();
        setManagedStartHold(null);
        setOperatorWarning(null);
        appendLog(`[START] NOT ACCEPTED · ${held}; Manager proves no Job was admitted`);
        return;
      }
      if (!reconciled.batch?.batch_id) {
        setOperatorWarning(`Start ${held} is ${reconciled.state}. No resubmission; reconcile again or void a proven unadmitted Start.`);
        return;
      }
      const batch = await getProgrammingBatch(reconciled.batch.batch_id);
      if (batch.start_id !== held) throw new Error("Manager Batch Start identity mismatch");
      // Reconciliation may first observe an already terminal Batch. Retain its
      // identity before releasing the Start hold so reload restores its time.
      writeManagedBatch(batch.batch_id);
      setManagedBatchRecoveryId(null);
      const snapshot = managedProductionSnapshot(batch, managedTopology);
      applyBatchSnapshot(snapshot, catalog);
      logManagedBatch(batch, managedTopology);
      if (batch.outcome == null) {
        writeManagedStart(held);
        setManagedStartHold(held);
        beginActivity();
        const generation = ++pollGenerationRef.current;
        const topology = managedTopology ?? await loadManagedTopology();
        void pollManagedBatch(batch.batch_id, catalog, generation, topology);
      } else if (batch.outcome === "OUTCOME_UNKNOWN"
                 || batch.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN")
                 || (batch.outcome === "PASS" && snapshot.state !== "success")) {
        writeManagedStart(held);
        setManagedStartHold(held);
        setOperatorWarning(`Manager Batch ${batch.batch_id} is not proven safe/complete. Reconcile its PPU Run or evidence before new work; never resubmit.`);
      } else {
        clearManagedStart();
        setManagedStartHold(null);
        setOperatorWarning(null);
      }
      appendLog(`[START] RECONCILED · ${held} · Batch ${batch.batch_id} · ${batch.outcome ?? "RUNNING"}`);
    } catch (reason) {
      setOperatorWarning(`Start ${held} still unresolved: ${reason instanceof Error ? reason.message : "unknown"} · no resubmission`);
    }
  }

  // Manual Repeat: START pressed while Sites wait continues ONLY the Sites
  // the operator marked "IC replaced" on their tile (a one-Site Session needs
  // no mark). The Manager dispatches each next Cycle itself.
  async function continueManagedSites() {
    const batchId = batchSnapshot?.batch_id;
    const chosen = continuingSites;
    if (!batchId || !chosen.length || managedContinueLock.current) return;
    managedContinueLock.current = true;
    try {
      for (const site of chosen) {
        try {
          const answer = await continueProgrammingBatch(batchId, {
            ppu_alias: site.ppu_id, site_id: site.site_id, continue_seq: site.continue_seq,
          });
          appendLog(`[BAT] CONTINUE · ${site.ppu_id} Site ${site.site_id} · IC replaced${answer.duplicate ? " · already accepted" : ""}`);
          if (catalog) applyBatchSnapshot(managedProductionSnapshot(answer.batch, managedTopology), catalog);
        } catch (error) {
          appendLog(`[BAT] CONTINUE REFUSED · ${site.ppu_id} Site ${site.site_id} · ${error instanceof Error ? error.message : "request failed"} · nothing was started`, "WARN");
        }
      }
    } finally {
      setReplacedMarks(new Set());
      managedContinueLock.current = false;
    }
  }

  async function executeBatch() {
    if (waitingSites.length) {
      await continueManagedSites();
      return;
    }
    await executeManagedBatch();
  }

  async function abortBatch() {
    const activeBatchId = batchSnapshot?.batch_id;
    if (!activeBatchId || !serverBatchRunning || serverBatchState === "stopping" || batchAborting) return;
    setBatchCommandState("aborting");
    appendLog(`[BAT] ABORT REQUESTED · ${activeBatchId}`, "WARN");
    try {
      const next = await stopProgrammingBatch(activeBatchId);
      if (catalog) applyBatchSnapshot(managedProductionSnapshot(next, managedTopology), catalog);
      setGatewayHealth("online");
    } catch (error) {
      setGatewayHealth(gatewayHealthFromError(error));
      appendLog(`[BAT] ABORT ERROR · ${error instanceof Error ? error.message : "unknown error"}`, "ERROR");
    } finally {
      setBatchCommandState("idle");
    }
  }

  function stateText(site: SiteRuntime): string {
    if (!site.enabled) return text.disabled;
    if (site.communicationState === "reconnecting") return "RECONNECTING";
    return text[site.state];
  }

  const programmingUnavailable = !catalog && gatewayHealth === "online" && Boolean(providerError);

  return (
    <main className="factoryConsoleV2" data-programming-backend="manager">
      <section className="factoryConsoleShell">
        <header className="factoryConsoleHeader">
          <h1>{text.title}</h1>
          <div className={`factoryProvider ${gatewayTone}`} aria-label="Factory communication health">
            <i /><span>{gatewayLabel} · {ppuHealth.label}</span><b>PMode</b>
          </div>
        </header>

        {!catalog && (
          <section className="factoryConsoleNotice" role="status">
            <b style={programmingUnavailable ? { color: "#475569" } : undefined}>
              {gatewayHealth === "unreachable" ? text.gatewayUnreachable : providerError ? text.offline : text.loading}
            </b>
            {providerError && gatewayHealth === "unreachable" && <span>{providerError}</span>}
          </section>
        )}

        {catalog && (
          <>
            <BatchSummary
              items={kpis}
              ariaLabel="Production Batch Summary"
              title="BATCH SUMMARY"
              meta={`${batchSnapshot ? "Current Batch" : "Batch Preview"} · ${statisticsMeta(statistics)}`}
            />

            <OperatorPanel
              number={1}
              title={text.systemSetup}
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
              <p className="selectionHint"><b>{text.productionSelection}</b> — {text.productionSelectionHint}</p>
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

            <ProgrammingJobPanel
              mode="production"
              title={text.programmingJob}
              collapsed={programmingJobCollapsed}
              onToggleCollapsed={() => setProgrammingJobCollapsed(current => !current)}
              expandLabel={text.showSelection}
              collapseLabel={text.hideSelection}
              targetDevice={targetDevice}
              onTargetChange={setTargetDevice}
              targetDisabled={batchRunning}
              targetLabel={text.targetIc}
              targetLevels={[1, 2, 3]}
              imageLabel="Programming Source"
              source={{ value: programmingSource, disabled: batchRunning, onChange: changeProgrammingSource }}
              image={{
                name: managedFile?.name
                  ?? (programmingSource === "bundle" ? "Select canonical Bundle v3 (.zip)…" : "Select programming image (.bin)…"),
                title: managedFile?.name,
                source: managedFile ? `user_${programmingSource}` : "none",
                hint: programmingSource === "bundle"
                  ? "Your own canonical Bundle v3. The Manager verifies it against the qualified Programming Route."
                  : "Binary Programming Image (.bin). The Manager builds the canonical Bundle v3.",
                browseLabel: text.browse,
                browseDisabled: batchRunning,
                inputDisabled: batchRunning,
                inputAriaLabel: `Production Programming ${programmingSource === "bundle" ? "Bundle" : "Image"} file`,
                accept: PROGRAMMING_SOURCE_ACCEPT[programmingSource],
                onFileChange: file => {
                  setManagedFile(file);
                  setBatchSnapshot(null);
                  clearManagedBatch();
                  loggedRecords.current.clear();
                  if (file) appendLog(`[IMG] SELECTED ${programmingSource.toUpperCase()} · ${file.name} · ${file.size} bytes`);
                },
              }}
              operationsLabel={text.operations}
              operations={managedOperationOptions.map(operation => ({
                key: operation,
                code: PROGRAMMING_OPERATION_LABELS[operation].code,
                label: PROGRAMMING_OPERATION_LABELS[operation].label,
                checked: managedOperations.includes(operation),
                disabled: batchRunning,
                onChange: () => setManagedOperations(current => current.includes(operation)
                  ? current.filter(value => value !== operation)
                  : [...current, operation]),
              }))}
              policyLabel={text.batchPolicy}
              policy={{
                repeatLabel: text.repeat,
                repeatValue: repeatCount,
                repeatDisabled: batchRunning,
                repeatAriaLabel: "Repeat Count",
                onRepeatChange: setRepeatCount,
                replaceIc: {
                  label: "Replace IC each Cycle",
                  checked: replaceIc,
                  disabled: batchRunning,
                  ariaLabel: "Replace IC before next Cycle",
                  onChange: setReplaceIc,
                },
                retryLabel: text.retry,
                retryValue: siteRetryLimit,
                retryMax: 5,
                retryDisabled: batchRunning,
                note: `Manager-owned Batch · Repeat 1–10000 Cycles per Site (a FAIL settles one Cycle; Retries never add one) · Retry 0–5 only for definite eligible FAIL (never OUTCOME UNKNOWN) · ABORT stops pending submissions but never cancels an accepted Job.${batchSnapshot?.awaiting_continue?.length ? ` · WAITING: ${batchSnapshot.awaiting_continue.map(site => `${site.ppu_id} Site ${site.site_id} — ${site.detail}`).join(" | ")} — replace the IC, tick that Site as replaced${(batchSnapshot?.sites.length ?? 0) > 1 ? "" : " (one-Site Session: not needed)"} and press START. Unmarked Sites keep waiting.` : ""}`,
                retryAriaLabel: "Site Retry Limit",
                onRetryChange: setSiteRetryLimit,
                stopLabel: text.stopPolicy,
                stopValue: failedSiteThreshold,
                stopDisabled: batchRunning || !batchCounts.sites,
                stopAriaLabel: "Stop Policy",
                stopOptions: [
                  { value: "", label: text.never },
                  ...Array.from({ length: batchCounts.sites }, (_, index) => index + 1).map(value => ({ value: String(value), label: `${value} Fail` })),
                ],
                onStopChange: setFailedSiteThreshold,
              }}
              startLabel={waitingSites.length
                ? continuingSites.length ? `${text.start} · CONTINUE ${continuingSites.map(site => `${site.ppu_id} ${siteLabel(site.site_id)}`).join(", ")}`
                  : `${text.start} · MARK THE REPLACED SITE(S)`
                : text.start}
              startDisabled={waitingSites.length ? !continuingSites.length : !batchReadiness.ready || !policyValid}
              onStart={executeBatch}
              statusLabel={text.batchStatus}
              statusValue={batchStatusLabel}
              statusClassName={`state-${batchStatusState}`}
              abortLabel={text.abort}
              abortDisabled={!serverBatchRunning || serverBatchState === "stopping" || batchAborting}
              onAbort={abortBatch}
            />

            {managedStartHold && !batchRunning && (
              <button className="ppuSiteButton" type="button" data-testid="reconcile-managed-start"
                onClick={() => void reconcileHeldManagerStart()}>
                RECONCILE MANAGER START
              </button>
            )}
            {!batchReadiness.ready && !batchRunning && managedReadiness.reason && (
              <div className="factoryWarning" role="status" data-testid="managed-readiness">
                <span><b>{managedReadiness.label}</b> · {managedReadiness.reason}</span>
              </div>
            )}
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
                  {groupedProductionTargets.map(group => {
                    const facilityId = group.facility.facility_id;
                    const totalSites = group.targets.reduce((total, active) => total + active.siteIds.length, 0);
                    const selectedSites = group.targets.reduce(
                      (total, active) => total + (displayedBatchSelection[facilityId]?.[active.target.ppu_id] ?? []).length,
                      0,
                    );
                    const allSelected = totalSites > 0 && selectedSites === totalSites;
                    const partiallySelected = selectedSites > 0 && selectedSites < totalSites;
                    return (
                      <section className="factoryFacilityGroup" key={facilityId} data-production-facility={facilityId}>
                        <header>
                          <div className="factoryFacilitySelection">
                            <input
                              type="checkbox"
                              aria-label={`Batch select ${group.facility.display_name}`}
                              checked={allSelected}
                              disabled={batchRunning}
                              ref={element => { if (element) element.indeterminate = partiallySelected; }}
                              onChange={() => toggleBatchFacility(facilityId, group.targets)}
                            />
                            <b>{group.facility.display_name}</b>
                          </div>
                          <span>{group.targets.length} PPUs · {selectedSites}/{totalSites} Sites selected</span>
                        </header>
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
                                  const pause = (batchSnapshot?.sites.length ?? 0) > 1
                                    ? waitingSites.find(item => item.ppu_id === active.target.ppu_id && item.site_id === site.id) : undefined;
                                  const waitingMark = pause ? continueMarkKey(pause.ppu_id, pause.site_id, pause.continue_seq) : null;
                                  return (
                                    <article
                                      className={`factorySiteLedCard state-${displayState} ${selected ? "batch-selected" : "batch-excluded"}`}
                                      data-production-site={site.id}
                                      data-site-state={displayState}
                                      data-batch-selected={selected ? "true" : "false"}
                                      aria-label={`${active.target.display_name} ${siteLabel(site.id)} ${stateText(site)}${site.currentRound ? ` ${roundUnit} ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}` : ""} ${selected ? "selected for Batch" : "excluded from Batch"}`}
                                      title={`${group.facility.display_name} / ${active.target.display_name} / ${siteLabel(site.id)} · ${stateText(site)}${site.currentRound ? ` · ${roundUnit} ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}` : ""}${site.operation ? ` · ${operationCodes[site.operation]} ${site.progress}%` : ""}`}
                                      key={site.id}
                                    >
                                      <div className="factorySiteLedCardTop">
                                        {waitingMark ? (
                                          // While THIS Site waits, its checkbox is the operator's
                                          // "IC replaced" mark for this pause only.
                                          <input
                                            type="checkbox"
                                            aria-label={`${active.target.display_name} ${siteLabel(site.id)} IC replaced`}
                                            data-site-replaced={`${active.target.ppu_id}:${site.id}`}
                                            checked={replacedMarks.has(waitingMark)}
                                            onChange={() => setReplacedMarks(current => {
                                              const next = new Set(current);
                                              if (next.has(waitingMark)) next.delete(waitingMark); else next.add(waitingMark);
                                              return next;
                                            })}
                                          />
                                        ) : (
                                          <input
                                            type="checkbox"
                                            aria-label={`Batch select ${active.target.display_name} ${siteLabel(site.id)}`}
                                            checked={selected}
                                            disabled={batchRunning || !site.enabled}
                                            onChange={() => toggleBatchSite(active, site.id)}
                                          />
                                        )}
                                        <b>{siteLabel(site.id)}</b>
                                      </div>
                                      <div className="factorySiteLed" data-state={displayState}><i /></div>
                                      <small>{site.communicationState === "reconnecting"
                                        ? `RETRY ${site.communicationAttempt ?? 1}`
                                        : displayState === "running" && site.currentRound
                                          ? `${roundUnit} ${site.currentRound}/${batchSnapshot?.execution_policy.repeat_count ?? repeatValue ?? 1}`
                                          : stateText(site)}</small>
                                    </article>
                                  );
                                })}
                              </div>
                            </section>
                          );
                        })}
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}
            </OperatorPanel>

            {batchSnapshot && batchSnapshot.error?.message && <div className="factoryRuntimeError">{batchSnapshot.error.error_code ? `${batchSnapshot.error.error_code} · ` : ""}{batchSnapshot.error.message}</div>}

            <ProductionLogPanel number={4} logs={logs} title={text.factoryLog} clearLabel={text.clearLog} onClear={() => setLogs([])} />
          </>
        )}
      </section>
    </main>
  );
}
