"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { BatchLifecycle } from "../batch-lifecycle";
import { evaluateBatchReadiness } from "../batch-readiness";
import { useI18n } from "../i18n";
import {
  cancelJob,
  engineeringTargetApiBase,
  getEngineeringTargets,
  getJob,
  getPPUStatus,
  PlasmaSubmissionBlockedError,
  readDownloadUrl,
  startJob,
} from "../plasma-api";
import type {
  EngineeringTargetCatalog,
  AssetTransferEvent,
  JobSnapshot,
  JobState,
  Operation,
  PPUSnapshot,
  SiteSnapshot,
} from "../plasma-api";
import { useWorkspaceSession, type TargetSelection } from "../workspace-session";
import { ActiveFpsSummary, BatchPolicyPanel, BatchTopologySummary } from "../batch-dashboard-panels";
import "../programming-batch-toolbar.css";
import EngineeringLogPanel, {
  classifyEngineeringLog,
  engineeringLogCategoryLabel,
  type EngineeringLogCategory,
  type EngineeringLogEntry,
} from "./engineering-log-panel";

type Stage =
  | "idle"
  | "queued"
  | "erase"
  | "program"
  | "verify"
  | "read"
  | "success"
  | "cancelled"
  | "failed"
  | "faulted"
  | "error"
  | "stopped"
  | "timeout"
  | "aborted";

type Site = {
  id: number;
  enabled: boolean;
  stage: Stage;
  progress: number;
  operation?: Operation;
  jobId?: string;
  target?: string;
  interface?: string;
  error?: string;
  outputFile?: string;
};

type ConnectionState = "connecting" | "online" | "offline";
type BatchSiteState = "running" | "cancelling" | "success" | "cancelled" | "faulted" | "error" | "stopped";
type BatchTerminalState = "success" | "cancelled" | "faulted" | "error" | "stopped";
type PendingRestore = {
  target: TargetSelection;
  siteIds: number[] | null;
  targetRestored: boolean;
};

const MAX_IMAGE_ASSET_BYTES = 16 * 1024 * 1024;
const MAX_LOG_ENTRIES = 1000;
const POLL_INTERVAL_MS = 500;
const POLL_ATTEMPTS = 600;
const runningStages: Stage[] = ["queued", "erase", "program", "verify", "read"];
const terminalStates = new Set<JobState>(["success", "failed", "cancelled", "timeout", "aborted"]);
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };

function isRunning(site: Site): boolean {
  return runningStages.includes(site.stage);
}

function uiStage(job: JobSnapshot): Stage {
  if (job.state === "running") {
    if (job.stage === "erase" || job.stage === "program" || job.stage === "verify") return job.stage;
    if (job.stage?.startsWith("read_")) return "read";
    return "queued";
  }
  if (job.state === "queued") return "queued";
  return job.state;
}

function siteFromStatus(snapshot: SiteSnapshot, existing?: Site): Site {
  const runtimeStage: Stage = snapshot.current_job_id || snapshot.state === "running" || snapshot.state === "queued"
    ? "queued"
    : "idle";
  return {
    id: snapshot.site_id,
    enabled: snapshot.enabled,
    stage: existing?.stage ?? runtimeStage,
    progress: existing?.progress ?? 0,
    operation: existing?.operation,
    jobId: snapshot.current_job_id ?? existing?.jobId,
    target: snapshot.target ?? undefined,
    interface: snapshot.interface ?? undefined,
    error: existing?.error,
    outputFile: existing?.outputFile,
  };
}

function initialSelection(catalog: EngineeringTargetCatalog): TargetSelection {
  const facility = catalog.facilities[0];
  return {
    facilityId: facility?.facility_id ?? "",
    ppuId: facility?.ppus[0]?.ppu_id ?? "",
  };
}

function validSelection(catalog: EngineeringTargetCatalog, selection: TargetSelection): TargetSelection {
  const facility = catalog.facilities.find(item => item.facility_id === selection.facilityId);
  if (!facility) return initialSelection(catalog);
  if (!facility.ppus.some(item => item.ppu_id === selection.ppuId)) return initialSelection(catalog);
  return selection;
}

function imageAssetSizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
  return `${(bytes / 1024).toFixed(1)} KiB`;
}

function shortSha256(sha256: string): string {
  return `${sha256.slice(0, 12)}…`;
}

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function siteListLabel(ids: number[]): string {
  return ids.length ? ids.map(siteLabel).join(", ") : "none";
}

function operationListLabel(operations: Operation[]): string {
  return operations.length ? operations.map(item => item.toUpperCase()).join(" → ") : "none";
}

function sameTarget(left: TargetSelection, right: TargetSelection): boolean {
  return left.facilityId === right.facilityId && left.ppuId === right.ppuId;
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

export default function ProgrammingWorkspace() {
  const { locale, t } = useI18n();
  const {
    hydrated: workspaceHydrated,
    apiBase,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    programmingImage: imageAsset,
    setProgrammingImage: setImageAsset,
    emodeSelection: selection,
    setEmodeSelection: setSelection,
    emodeSiteIds: selectedSiteIdsState,
    setEmodeSiteIds: setSelectedSiteIdsState,
    emodeOperations: selectedOperations,
    setEmodeOperations: setSelectedOperations,
    emodeReadOffset: readOffset,
    setEmodeReadOffset: setReadOffset,
    emodeReadLength: readLength,
    setEmodeReadLength: setReadLength,
  } = useWorkspaceSession();
  const [apiDraft, setApiDraft] = useState(apiBase);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [connectionGeneration, setConnectionGeneration] = useState(0);
  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [ppu, setPPU] = useState<PPUSnapshot | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [operatorWarning, setOperatorWarning] = useState<string | null>(null);
  const [submittingSiteIds, setSubmittingSiteIds] = useState<number[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchCancelling, setBatchCancelling] = useState(false);
  const [batchSiteStates, setBatchSiteStates] = useState<Record<number, BatchSiteState>>({});
  const [repeatCount, setRepeatCount] = useState("1");
  const [siteRetryLimit, setSiteRetryLimit] = useState("0");
  const [failedSiteThreshold, setFailedSiteThreshold] = useState("");
  const [logs, setLogs] = useState<EngineeringLogEntry[]>([]);

  const trackedJobs = useRef<Record<number, string>>({});
  const submissionGenerations = useRef<Record<number, number>>({});
  const batchLifecycle = useRef<BatchLifecycle | null>(null);
  const batchStopReason = useRef<"operator" | "threshold" | null>(null);
  const operatorCancelledSites = useRef<Set<number>>(new Set());
  const cancelRequests = useRef<Set<string>>(new Set());
  const imageInputRef = useRef<HTMLInputElement>(null);
  const logSequence = useRef(0);
  const initialSelectionKey = selection.facilityId && selection.ppuId
    ? `${selection.facilityId}/${selection.ppuId}`
    : null;
  const siteSelectionTarget = useRef<string | null>(selectedSiteIdsState !== null ? initialSelectionKey : null);
  const pendingRestore = useRef<PendingRestore | null>(null);
  const restartSessionRequested = useRef(false);

  const facility = catalog?.facilities.find(item => item.facility_id === selection.facilityId) ?? null;
  const selectedPPU = facility?.ppus.find(item => item.ppu_id === selection.ppuId) ?? null;
  const syntheticMockImageAvailable = selectedPPU?.provider === "mock";
  const targetSelectionKey = selection.facilityId && selection.ppuId
    ? `${selection.facilityId}/${selection.ppuId}`
    : null;
  const targetApiBase = catalog && selection.facilityId && selection.ppuId
    ? engineeringTargetApiBase(apiBase, selection.facilityId, selection.ppuId)
    : null;
  const selectedSiteIds = selectedSiteIdsState ?? [];
  const selectedSites = sites.filter(site => selectedSiteIds.includes(site.id));
  const readRangeValid = Number.isInteger(Number(readOffset))
    && Number(readOffset) >= 0
    && Number.isInteger(Number(readLength))
    && Number(readLength) > 0;
  const targetLocked = batchRunning || submittingSiteIds.length > 0 || sites.some(isRunning);
  const requiresImage = selectedOperations.some(operation => operation === "program" || operation === "verify");
  const allSitesExecutable = selectedSites.length === selectedSiteIds.length
    && selectedSites.length > 0
    && selectedSites.every(site => site.enabled && !isRunning(site) && !submittingSiteIds.includes(site.id));
  const batchReadiness = evaluateBatchReadiness({
    providerOnline: connection === "online" && Boolean(catalog),
    targetValid: Boolean(targetApiBase && selectedPPU),
    selectedSiteCount: selectedSiteIds.length,
    selectedOperationCount: selectedOperations.length,
    requiresImage,
    imagePresent: Boolean(imageAsset) || syntheticMockImageAvailable,
    imageValid: !imageAsset || imageAsset.size <= MAX_IMAGE_ASSET_BYTES,
    readSelected: selectedOperations.includes("read"),
    readParamsValid: readRangeValid,
    allSitesExecutable,
    batchRunning: batchRunning && !batchCancelling,
    batchCancelling,
  });
  const noOperationWarning = locale === "zh-TW"
    ? "未選擇任何操作。請至少選擇 Erase、Program、Verify 或 Read 其中一項。"
    : "No operation selected. Select at least one of Erase, Program, Verify, or Read.";
  const dismissWarning = locale === "zh-TW" ? "關閉警告" : "Dismiss warning";
  const syntheticImageLabel = locale === "zh-TW" ? "Mock Synthetic Image" : "Mock Synthetic Image";
  const syntheticImageHint = locale === "zh-TW"
    ? "未選 Image 時由 Mock Settings 的 Default Image Size 自動產生 Synthetic Image；手動選檔時以選檔優先。"
    : "Without a selected Image, Mock generates a Synthetic Image from Default Image Size; a selected file takes precedence.";
  const repeatValue = parsePositiveInt(repeatCount);
  const retryValue = parseNonNegativeInt(siteRetryLimit);
  const thresholdValue = failedSiteThreshold.trim() === "" ? null : parsePositiveInt(failedSiteThreshold);
  const policyValid = repeatValue !== null
    && repeatValue <= 10_000
    && retryValue !== null
    && retryValue <= 20
    && (failedSiteThreshold.trim() === "" || (thresholdValue !== null && thresholdValue <= selectedSiteIds.length));
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
  const activeFpsCounts = (() => {
    const batchStates = selectedSiteIds.map(siteId => batchSiteStates[siteId]).filter(Boolean) as BatchSiteState[];
    if (batchStates.length > 0) {
      const count = (state: BatchSiteState) => batchStates.filter(item => item === state).length;
      return {
        selected: selectedSiteIds.length,
        running: count("running") + count("cancelling"),
        pass: count("success"),
        faulted: count("faulted"),
        error: count("error"),
        stopped: count("stopped"),
        cancelled: count("cancelled"),
      };
    }
    return {
      selected: selectedSiteIds.length,
      running: selectedSites.filter(isRunning).length,
      pass: selectedSites.filter(site => site.stage === "success").length,
      faulted: selectedSites.filter(site => site.stage === "faulted").length,
      error: selectedSites.filter(site => site.stage === "failed" || site.stage === "error" || site.stage === "timeout" || site.stage === "aborted").length,
      stopped: selectedSites.filter(site => site.stage === "stopped").length,
      cancelled: selectedSites.filter(site => site.stage === "cancelled").length,
    };
  })();

  const appendLog = useCallback((
    message: string,
    error = false,
    category?: EngineeringLogCategory,
  ) => {
    const resolvedCategory = category ?? classifyEngineeringLog(message);
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs(current => [
      {
        id: ++logSequence.current,
        text: `${time}  [${engineeringLogCategoryLabel(resolvedCategory)}] ${message}`,
        error,
        category: resolvedCategory,
      },
      ...current,
    ].slice(0, MAX_LOG_ENTRIES));
  }, []);

  const logAssetEvent = useCallback((event: AssetTransferEvent) => {
    const digest = `SHA256 ${shortSha256(event.asset_sha256)}`;
    if (event.kind === "cache_check") {
      appendLog(`[IMG] CACHE CHECK · ${event.asset_name} · ${imageAssetSizeLabel(event.asset_size)} · ${digest} · fingerprint only`);
    } else if (event.kind === "cache_hit") {
      appendLog(`[IMG] CACHE HIT · ${digest} · reference only · no binary upload`);
    } else if (event.kind === "cache_miss") {
      appendLog(`[IMG] CACHE MISS · ${digest}`);
    } else if (event.kind === "upload_start") {
      appendLog(`[IMG] UPLOAD START · ${event.asset_name} · ${imageAssetSizeLabel(event.asset_size)} · ${digest}`);
    } else {
      appendLog(`[IMG] UPLOAD COMPLETE · ${event.asset_name} · ${imageAssetSizeLabel(event.asset_size)} · ${digest}`);
    }
  }, [appendLog]);

  const resetTargetRuntime = useCallback((preserveSiteSelection = false) => {
    trackedJobs.current = {};
    submissionGenerations.current = {};
    cancelRequests.current.clear();
    batchLifecycle.current = null;
    batchStopReason.current = null;
    operatorCancelledSites.current.clear();
    setPPU(null);
    setSites([]);
    if (!preserveSiteSelection) {
      siteSelectionTarget.current = null;
      setSelectedSiteIdsState(null);
    }
    setBatchSiteStates({});
    setSubmittingSiteIds([]);
    setBatchRunning(false);
    setBatchCancelling(false);
  }, [setSelectedSiteIdsState]);

  const switchTarget = useCallback((next: TargetSelection) => {
    pendingRestore.current = null;
    resetTargetRuntime();
    setSelection(next);
    if (next.facilityId && next.ppuId) appendLog(`[TARGET] ${next.facilityId} / ${next.ppuId}`);
  }, [appendLog, resetTargetRuntime, setSelection]);

  const applyJob = useCallback((job: JobSnapshot) => {
    const stage = uiStage(job);
    const outputFile = job.result?.output_files?.[0]?.split(/[\\/]/).pop();
    const error = job.result?.error?.message;
    setSites(current => current.map(site => site.id === job.site_id ? {
      ...site,
      stage,
      operation: job.operation,
      progress: Number(job.progress_percent ?? 0),
      jobId: job.job_id,
      outputFile,
      error,
    } : site));
  }, []);

  useEffect(() => {
    if (!workspaceHydrated) return;
    queueMicrotask(() => setApiDraft(apiBase));
  }, [apiBase, workspaceHydrated]);

  useEffect(() => {
    if (!workspaceHydrated) return;
    let cancelled = false;
    void (async () => {
      try {
        const sessionId = restartSessionRequested.current
          ? await restartEngineeringSession(apiBase)
          : await ensureEngineeringSession(apiBase);
        restartSessionRequested.current = false;
        if (cancelled) return;
        appendLog(`[SESSION] ACTIVE · ${sessionId.slice(0, 8)}…`);
        const next = await getEngineeringTargets(apiBase);
        if (cancelled) return;
        setCatalog(next);
        setCatalogError(null);
        setConnection("online");
        const restore = pendingRestore.current;
        if (restore) {
          const resolved = validSelection(next, restore.target);
          setSelection(resolved);
          restore.targetRestored = sameTarget(resolved, restore.target);
          if (restore.targetRestored) {
            appendLog(`[TARGET] RESTORED · ${restore.target.facilityId} / ${restore.target.ppuId}`, false, "SYS");
          } else {
            pendingRestore.current = null;
          }
        } else {
          setSelection(current => validSelection(next, current));
        }
        appendLog(`[ENGINEERING] Provider ${next.provider.toUpperCase()} · ${next.facility_count} Facilities · ${next.ppu_count} PPUs · ${next.site_count} Sites`);
      } catch (error) {
        restartSessionRequested.current = false;
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "Engineering target provider unavailable";
        resetTargetRuntime(true);
        setCatalog(null);
        setCatalogError(message);
        setConnection("offline");
        appendLog(`[ENGINEERING] Provider unavailable · ${message}`, true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, connectionGeneration, appendLog, ensureEngineeringSession, resetTargetRuntime, restartEngineeringSession, setSelection, workspaceHydrated]);

  useEffect(() => {
    if (!targetApiBase || !targetSelectionKey) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const submissionSnapshot = { ...submissionGenerations.current };
        const status = await getPPUStatus(targetApiBase!);
        if (stopped) return;
        setPPU(status.ppu ?? null);
        const availableIds = new Set(status.sites.map(site => site.site_id));
        Object.keys(trackedJobs.current).forEach(siteId => {
          if (!availableIds.has(Number(siteId))) delete trackedJobs.current[Number(siteId)];
        });
        status.sites.forEach(site => {
          const changed = (submissionGenerations.current[site.site_id] ?? 0)
            !== (submissionSnapshot[site.site_id] ?? 0);
          if (site.current_job_id && !changed) trackedJobs.current[site.site_id] = site.current_job_id;
        });
        setSites(current => status.sites.map(snapshot => (
          siteFromStatus(snapshot, current.find(site => site.id === snapshot.site_id))
        )));
        const enabledIds = status.sites.filter(site => site.enabled).map(site => site.site_id);
        const restore = pendingRestore.current;
        if (restore?.targetRestored && sameTarget(restore.target, selection)) {
          siteSelectionTarget.current = targetSelectionKey;
          if (restore.siteIds === null) {
            setSelectedSiteIdsState(enabledIds);
          } else {
            const restoredIds = restore.siteIds.filter(id => availableIds.has(id));
            setSelectedSiteIdsState(restoredIds);
            appendLog(`[SITE] RESTORED · ${siteListLabel(restoredIds)}`, false, "SYS");
          }
          pendingRestore.current = null;
        } else {
          setSelectedSiteIdsState(current => {
            if (siteSelectionTarget.current !== targetSelectionKey) {
              siteSelectionTarget.current = targetSelectionKey;
              return enabledIds;
            }
            if (current === null) return enabledIds;
            return current.filter(id => availableIds.has(id));
          });
        }

        const jobIds = [...new Set(Object.values(trackedJobs.current))];
        const jobs = await Promise.all(jobIds.map(jobId => getJob(targetApiBase!, jobId)));
        if (stopped) return;
        jobs.forEach(job => {
          if (trackedJobs.current[job.site_id] !== job.job_id) return;
          applyJob(job);
          if (terminalStates.has(job.state)) delete trackedJobs.current[job.site_id];
        });
      } catch (error) {
        if (!stopped) appendLog(`[TARGET] Status failed · ${error instanceof Error ? error.message : "unknown error"}`, true, "PPU");
      } finally {
        if (!stopped) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [targetApiBase, targetSelectionKey, connectionGeneration, selection, applyJob, appendLog, setSelectedSiteIdsState]);

  function connect(event: FormEvent) {
    event.preventDefault();
    appendLog(`[CONNECTION] CONNECT · ${apiDraft}`, false, "USR");
    if (targetLocked) {
      appendLog("[NET] Gateway change blocked while a target Job is active", true);
      return;
    }
    try {
      pendingRestore.current = selection.facilityId && selection.ppuId
        ? {
          target: { ...selection },
          siteIds: selectedSiteIdsState === null ? null : [...selectedSiteIdsState],
          targetRestored: false,
        }
        : null;
      resetTargetRuntime(true);
      setCatalog(null);
      setCatalogError(null);
      setConnection("connecting");
      restartSessionRequested.current = true;
      const normalized = setApiBase(apiDraft);
      setApiDraft(normalized);
      setConnectionGeneration(current => current + 1);
    } catch (error) {
      appendLog(`[NET] ${error instanceof Error ? error.message : "Invalid Gateway URL"}`, true);
    }
  }

  function selectFacility(facilityId: string) {
    if (targetLocked) return;
    const nextFacility = catalog?.facilities.find(item => item.facility_id === facilityId);
    const next = {
      facilityId,
      ppuId: nextFacility?.ppus[0]?.ppu_id ?? "",
    };
    appendLog(`[TARGET] SELECT · ${next.facilityId} / ${next.ppuId || "none"}`, false, "USR");
    switchTarget(next);
  }

  function selectPPU(ppuId: string) {
    if (targetLocked) return;
    appendLog(`[TARGET] SELECT · ${selection.facilityId} / ${ppuId}`, false, "USR");
    switchTarget({ facilityId: selection.facilityId, ppuId });
  }

  function toggleSite(siteId: number) {
    if (batchRunning) return;
    setBatchSiteStates({});
    if (targetSelectionKey) siteSelectionTarget.current = targetSelectionKey;
    const next = selectedSiteIds.includes(siteId)
      ? selectedSiteIds.filter(id => id !== siteId)
      : [...selectedSiteIds, siteId].sort((left, right) => left - right);
    setSelectedSiteIdsState(next);
    appendLog(`[SITE] SELECTION · ${siteListLabel(next)}`, false, "USR");
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setOperatorWarning(null);
    const next = selectedOperations.includes(operation)
      ? selectedOperations.filter(item => item !== operation)
      : operationOrder.filter(item => selectedOperations.includes(item) || item === operation);
    setSelectedOperations(next);
    appendLog(`[BATCH] OPERATIONS · ${operationListLabel(next)}`, false, "USR");
  }

  function selectImageAsset(file: File | null) {
    setImageAsset(file);
    appendLog(
      file
        ? `[IMG] SELECT · ${file.name} · ${imageAssetSizeLabel(file.size)}`
        : "[IMG] CLEAR",
      false,
      "USR",
    );
  }

  function operationDisabled(site: Site, operation: Operation, forBatch = false): boolean {
    if (!targetApiBase || connection !== "online" || !site.enabled || isRunning(site)) return true;
    if (!forBatch && batchRunning) return true;
    if (submittingSiteIds.includes(site.id)) return true;
    if ((operation === "program" || operation === "verify") && !imageAsset && !syntheticMockImageAvailable) return true;
    if ((operation === "program" || operation === "verify") && Boolean(imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES)) return true;
    if (operation === "read" && !readRangeValid) return true;
    return false;
  }

  function setBatchSiteState(siteId: number, state: BatchSiteState) {
    setBatchSiteStates(current => ({ ...current, [siteId]: state }));
  }

  function clearBatchSiteState(siteId: number) {
    setBatchSiteStates(current => {
      if (!(siteId in current)) return current;
      const next = { ...current };
      delete next[siteId];
      return next;
    });
  }

  async function runSite(
    siteId: number,
    operation: Operation,
    forBatch = false,
    submissionGuard?: () => boolean,
  ): Promise<JobSnapshot | undefined> {
    if (!targetApiBase) return;
    const site = sites.find(item => item.id === siteId);
    if (!site || operationDisabled(site, operation, forBatch)) return;
    if (!forBatch) clearBatchSiteState(siteId);
    submissionGenerations.current[siteId] = (submissionGenerations.current[siteId] ?? 0) + 1;
    setSubmittingSiteIds(current => current.includes(siteId) ? current : [...current, siteId]);
    try {
      const usesSyntheticImage = (operation === "program" || operation === "verify")
        && !imageAsset
        && syntheticMockImageAvailable;
      if (usesSyntheticImage) {
        appendLog(`[IMG] SYNTHETIC · ${siteLabel(siteId)} · ${operation.toUpperCase()} · Mock Settings Default Image Size`);
      }
      const job = await startJob(targetApiBase, {
        siteId,
        operation,
        assetFile: operation === "erase" || operation === "read" ? null : imageAsset,
        engineeringSessionId: engineeringSessionId ?? undefined,
        allowSyntheticMockImage: usesSyntheticImage,
        offset: operation === "read" ? Number(readOffset) : undefined,
        length: operation === "read" ? Number(readLength) : undefined,
        submissionGuard,
        onAssetEvent: logAssetEvent,
      });
      trackedJobs.current[siteId] = job.job_id;
      setSites(current => current.map(item => item.id === siteId ? {
        ...item,
        stage: "queued",
        operation,
        progress: 0,
        jobId: job.job_id,
        outputFile: undefined,
        error: undefined,
      } : item));
      appendLog(`[${siteLabel(siteId)}] ${operation.toUpperCase()} accepted · ${job.job_id}`);
      return job;
    } catch (error) {
      if (error instanceof PlasmaSubmissionBlockedError) return;
      const message = error instanceof Error ? error.message : "unknown error";
      appendLog(`[${siteLabel(siteId)}] Submit failed · ${message}`, true);
      setSites(current => current.map(item => item.id === siteId ? {
        ...item,
        stage: "failed",
        operation,
        error: message,
      } : item));
    } finally {
      setSubmittingSiteIds(current => current.filter(id => id !== siteId));
    }
  }

  function runSingleSite(siteId: number, operation: Operation) {
    setBatchSiteStates({});
    const readDetail = operation === "read" ? ` · offset ${readOffset} · length ${readLength}` : "";
    appendLog(`[${siteLabel(siteId)}] EXECUTE ${operation.toUpperCase()}${readDetail}`, false, "USR");
    void runSite(siteId, operation);
  }

  async function waitTerminal(job: JobSnapshot): Promise<JobSnapshot> {
    if (!targetApiBase) throw new Error("No Engineering PPU target selected");
    for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
      const current = await getJob(targetApiBase, job.job_id);
      applyJob(current);
      if (terminalStates.has(current.state)) return current;
      await new Promise(resolve => window.setTimeout(resolve, POLL_INTERVAL_MS));
    }
    throw new Error(`${job.job_id} timed out waiting for completion`);
  }

  async function requestCancel(siteId: number, jobId: string) {
    if (!targetApiBase || cancelRequests.current.has(jobId)) return;
    cancelRequests.current.add(jobId);
    try {
      await cancelJob(targetApiBase, jobId);
      appendLog(`[${siteLabel(siteId)}] Cancel requested · ${jobId}`);
    } catch (error) {
      cancelRequests.current.delete(jobId);
      appendLog(`[${siteLabel(siteId)}] Cancel failed · ${error instanceof Error ? error.message : "unknown error"}`, true);
    }
  }

  async function runBatch() {
    if (batchRunning) return;
    if (!batchReadiness.ready) {
      if (batchReadiness.code === "no-op") setOperatorWarning(noOperationWarning);
      appendLog(`[BATCH] BLOCKED · ${batchReadiness.label}`, false, "USR");
      return;
    }
    if (!policyValid || repeatValue === null || retryValue === null) {
      setOperatorWarning(dashboardCopy.policy.invalid);
      appendLog(`[BATCH] BLOCKED · ${dashboardCopy.policy.invalid}`, false, "USR");
      return;
    }
    setOperatorWarning(null);
    const siteIds = [...selectedSiteIds];
    const operations = [...selectedOperations];
    const readDetail = operations.includes("read") ? ` · read offset ${readOffset} · length ${readLength}` : "";
    appendLog(
      `[BATCH] EXECUTE · ${operationListLabel(operations)} · ${siteListLabel(siteIds)} · repeat ${repeatValue} · retry ${retryValue} · threshold ${thresholdValue ?? "off"}${readDetail}`,
      false,
      "USR",
    );
    const lifecycle = new BatchLifecycle(siteIds);
    const results: Partial<Record<number, BatchTerminalState>> = {};
    const faultedSites = new Set<number>();
    batchLifecycle.current = lifecycle;
    batchStopReason.current = null;
    operatorCancelledSites.current.clear();
    setBatchRunning(true);
    setBatchCancelling(false);
    setBatchSiteStates(Object.fromEntries(siteIds.map(id => [id, "running"])) as Record<number, BatchSiteState>);
    appendLog(`START ${operations.map(item => item.toUpperCase()).join(" → ")} · ${siteListLabel(siteIds)}`, false, "BAT");

    const terminalize = (siteId: number, state: BatchTerminalState, error?: string) => {
      results[siteId] = state;
      setBatchSiteState(siteId, state);
      if (state === "faulted" || state === "error" || state === "stopped") {
        setSites(current => current.map(site => site.id === siteId ? { ...site, stage: state, error: error ?? site.error } : site));
      }
      lifecycle.finish(siteId);
    };
    const cancellationState = (siteId: number): BatchTerminalState => {
      if (operatorCancelledSites.current.has(siteId)) return "cancelled";
      return batchStopReason.current === "threshold" ? "stopped" : "cancelled";
    };
    const triggerThresholdIfNeeded = async () => {
      if (thresholdValue === null || faultedSites.size < thresholdValue || batchStopReason.current) return;
      batchStopReason.current = "threshold";
      setBatchCancelling(true);
      setBatchSiteStates(current => Object.fromEntries(Object.entries(current).map(([siteId, state]) => [
        siteId,
        state === "running" ? "cancelling" : state,
      ])) as Record<number, BatchSiteState>);
      const { activeJobs } = lifecycle.cancel();
      appendLog(`[BATCH] THRESHOLD · ${faultedSites.size}/${thresholdValue} FAULTED · stopping unfinished Sites`, true, "BAT");
      await Promise.all(activeJobs.map(([siteId, jobId]) => requestCancel(siteId, jobId)));
    };

    try {
      await Promise.all(siteIds.map(async siteId => {
        for (let round = 1; round <= repeatValue; round += 1) {
for (const operation of operations) {
  let operationSucceeded = false;
  for (let attempt = 0; attempt <= retryValue; attempt += 1) {
    if (batchStopReason.current === "threshold") {
      terminalize(siteId, cancellationState(siteId));
      return;
    }
    if (!lifecycle.prepare(siteId, operation)) {
      terminalize(siteId, cancellationState(siteId));
      return;
    }
    await new Promise(resolve => window.setTimeout(resolve, 0));
    if (!lifecycle.beginSubmit(siteId)) {
      terminalize(siteId, cancellationState(siteId));
      return;
    }
    const job = await runSite(siteId, operation, true, () => lifecycle.canDispatch(siteId));
    if (!job) {
      if (lifecycle.isCancelRequested(siteId)) terminalize(siteId, cancellationState(siteId));
      else terminalize(siteId, "error", "Job submission failed");
      return;
    }
    if (lifecycle.accepted(siteId, job.job_id)) await requestCancel(siteId, job.job_id);
    let finalJob: JobSnapshot;
    try {
      finalJob = await waitTerminal(job);
    } catch (error) {
      if (lifecycle.isCancelRequested(siteId)) terminalize(siteId, cancellationState(siteId));
      else terminalize(siteId, "error", error instanceof Error ? error.message : "Batch polling failed");
      return;
    }
    if (lifecycle.isCancelRequested(siteId) || cancelRequests.current.has(job.job_id)) {
      terminalize(siteId, cancellationState(siteId));
      return;
    }
    if (finalJob.state === "success") {
      operationSucceeded = true;
      break;
    }
    if (finalJob.state === "failed") {
      if (attempt < retryValue) {
        appendLog(`[${siteLabel(siteId)}] RETRY ${attempt + 1}/${retryValue} · Round ${round}/${repeatValue} · ${operation.toUpperCase()}`, false, "BAT");
        continue;
      }
      faultedSites.add(siteId);
      terminalize(siteId, "faulted", finalJob.result?.error?.message);
      await triggerThresholdIfNeeded();
      return;
    }
    if (finalJob.state === "cancelled") {
      terminalize(siteId, cancellationState(siteId));
      return;
    }
    terminalize(siteId, "error", finalJob.result?.error?.message ?? finalJob.state.toUpperCase());
    return;
  }
  if (!operationSucceeded) return;
}
        }
        terminalize(siteId, "success");
      }));

      const successful = siteIds.filter(siteId => results[siteId] === "success");
      const cancelled = siteIds.filter(siteId => results[siteId] === "cancelled");
      const faulted = siteIds.filter(siteId => results[siteId] === "faulted");
      const errors = siteIds.filter(siteId => results[siteId] === "error");
      const stopped = siteIds.filter(siteId => results[siteId] === "stopped");
      const groups: string[] = [];
      if (successful.length > 0) groups.push(`success: ${siteListLabel(successful)}`);
      if (faulted.length > 0) groups.push(`faulted: ${siteListLabel(faulted)}`);
      if (errors.length > 0) groups.push(`error: ${siteListLabel(errors)}`);
      if (stopped.length > 0) groups.push(`stopped: ${siteListLabel(stopped)}`);
      if (cancelled.length > 0) groups.push(`cancelled: ${siteListLabel(cancelled)}`);
      const outcome = errors.length > 0 || stopped.length > 0
        ? "ERROR"
        : faulted.length > 0
? "PARTIAL"
: cancelled.length === siteIds.length
  ? "CANCELLED"
  : cancelled.length > 0
    ? "PARTIAL"
    : "COMPLETE";
      appendLog(`${outcome} · ${groups.join(" · ")}`, errors.length > 0 || faulted.length > 0 || stopped.length > 0, "BAT");
    } finally {
      if (batchLifecycle.current === lifecycle) batchLifecycle.current = null;
      setBatchRunning(false);
      setBatchCancelling(false);
    }
  }

  async function cancelBatch() {
    const lifecycle = batchLifecycle.current;
    if (!batchRunning || batchCancelling || !lifecycle) return;
    appendLog("[BATCH] CANCEL", false, "USR");
    batchStopReason.current = "operator";
    const { activeJobs } = lifecycle.cancel();
    setBatchCancelling(true);
    setBatchSiteStates(current => Object.fromEntries(
      Object.entries(current).map(([siteId, state]) => [siteId, state === "running" ? "cancelling" : state]),
    ) as Record<number, BatchSiteState>);
    await Promise.all(activeJobs.map(([siteId, jobId]) => requestCancel(siteId, jobId)));
  }

  async function cancelSite(siteId: number) {
    const site = sites.find(item => item.id === siteId);
    if (!site?.jobId || !isRunning(site)) return;
    appendLog(`[${siteLabel(siteId)}] CANCEL`, false, "USR");
    const lifecycle = batchLifecycle.current;
    if (batchRunning && lifecycle) {
      operatorCancelledSites.current.add(siteId);
      const jobId = lifecycle.cancelSite(siteId);
      setBatchSiteState(siteId, "cancelling");
      if (jobId) await requestCancel(siteId, jobId);
      return;
    }
    await requestCancel(siteId, site.jobId);
  }

  return (
    <section className="engineeringProgramming" aria-label={t("engineeringProgramming.workspace")}>
      <div className="engineeringProgrammingHeader">
        <div>
          <p>ENGINEERING / PROGRAMMING</p>
          <h2>{t("engineeringProgramming.title")}</h2>
          <span>{t("engineeringProgramming.subtitle")}</span>
        </div>
        <form className={`engineeringGateway ${connection}`} onSubmit={connect}>
          <span className="pulse" />
          <label>
            <small>{t("engineeringProgramming.gateway")}</small>
            <input aria-label="Engineering Gateway URL" value={apiDraft} disabled={targetLocked} onChange={event => setApiDraft(event.target.value)} />
          </label>
          <button type="submit" disabled={targetLocked}>{t("engineeringProgramming.connect")}</button>
        </form>
      </div>

      <BatchTopologySummary
        facilityCount={catalog?.facility_count ?? 0}
        ppuCount={catalog?.ppu_count ?? 0}
        selectedSiteCount={selectedSiteIds.length}
        selectedFacilityCount={selection.facilityId ? 1 : 0}
        selectedPpuCount={selection.ppuId ? 1 : 0}
        counts={activeFpsCounts}
      />

      <section className="unifiedBatchControlStack" data-dashboard-mode="engineering">
      <section className="engineeringExecutionToolbar programmingBatchToolbar" aria-label="Engineering batch control">
        <div className="programmingBatchFile">
          <button type="button" className="engineeringBrowseButton" disabled={targetLocked} onClick={() => imageInputRef.current?.click()}>{t("engineeringProgramming.browse")}</button>
          <input ref={imageInputRef} aria-label="Engineering Programming Image Asset file" type="file" accept=".bin,application/octet-stream" hidden disabled={targetLocked} onChange={event => selectImageAsset(event.target.files?.[0] ?? null)} />
          <em
            className="programmingFileName"
            data-image-source={imageAsset ? "user" : requiresImage && syntheticMockImageAvailable ? "mock_synthetic" : "none"}
            title={imageAsset?.name}
          >
            {imageAsset?.name ?? (requiresImage && syntheticMockImageAvailable ? syntheticImageLabel : "—")}
          </em>
          <small className="programmingFileHint">{syntheticMockImageAvailable ? syntheticImageHint : t("engineeringProgramming.imageAssetHint")}</small>
        </div>
        <div className="programmingBatchOperations" role="group" aria-label="Engineering batch operations">
          <span>{t("engineeringProgramming.batchOperations")}</span>
          {operationOrder.map(operation => {
            const selected = selectedOperations.includes(operation);
            return <label key={operation} className={selected ? "selected" : ""}>
              <input type="checkbox" aria-label={`Engineering batch ${operation}`} checked={selected} disabled={batchRunning} onChange={() => toggleOperation(operation)} />
              <b>{operationCodes[operation]}</b>{t(`operation.${operation}`)}
            </label>;
          })}
        </div>
        <div className="programmingBatchActions">
          <div className={`batchReadiness readiness-${batchReadiness.code}`} role="status" aria-label="Batch readiness">
            <small>BATCH</small><b>{batchReadiness.label}</b>
          </div>
          <button type="button" className="executeBatch" onClick={() => void runBatch()} disabled={!batchReadiness.ready}>{t("selection.execute")}</button>
          <button type="button" className="cancelBatch" onClick={() => void cancelBatch()} disabled={!batchRunning || batchCancelling}>{t("selection.cancel")}</button>
        </div>
      </section>
      <BatchPolicyPanel
        repeatCount={repeatCount}
        retryLimit={siteRetryLimit}
        stopThreshold={failedSiteThreshold}
        maxThreshold={selectedSiteIds.length}
        disabled={batchRunning}
        valid={policyValid}
        copy={dashboardCopy.policy}
        onRepeatCount={setRepeatCount}
        onRetryLimit={setSiteRetryLimit}
        onStopThreshold={setFailedSiteThreshold}
      />
      </section>

      <ActiveFpsSummary counts={activeFpsCounts} copy={dashboardCopy.active} />

      {selectedOperations.includes("read") && (
        <section className="engineeringReadParameters" aria-label="Engineering READ parameters">
          <span>READ PARAMETERS</span>
          <label>Offset<input aria-label="Engineering READ offset" type="number" min="0" step="1" value={readOffset} disabled={batchRunning} onChange={event => setReadOffset(event.target.value)} /></label>
          <label>Length<input aria-label="Engineering READ length" type="number" min="1" step="1" value={readLength} disabled={batchRunning} onChange={event => setReadLength(event.target.value)} /></label>
        </section>
      )}

      {operatorWarning && (
        <div className="warning engineeringOperationWarning" role="alert">
          <span>{operatorWarning}</span>
          <button type="button" aria-label={dismissWarning} onClick={() => setOperatorWarning(null)}>×</button>
        </div>
      )}

      {imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES && <div className="warning">{t("engineeringProgramming.imageAssetTooLarge")}</div>}
      {catalogError && <div className="engineeringBoundaryNote warning"><b>{t("engineeringProgramming.providerOffline")}</b><span>{catalogError}</span></div>}

      <div className="engineeringTargetSelector">
        <label>
          <span>Facility</span>
          <select
            aria-label="Engineering Facility"
            value={selection.facilityId}
            disabled={!catalog || targetLocked}
            onChange={event => selectFacility(event.target.value)}
          >
            {(catalog?.facilities ?? []).map(item => <option key={item.facility_id} value={item.facility_id}>{item.display_name}</option>)}
          </select>
        </label>
        <label>
          <span>PPU</span>
          <select
            aria-label="Engineering PPU"
            value={selection.ppuId}
            disabled={!facility || targetLocked}
            onChange={event => selectPPU(event.target.value)}
          >
            {(facility?.ppus ?? []).map(item => (
              <option key={item.ppu_id} value={item.ppu_id}>{item.display_name} — {item.site_count} Sites</option>
            ))}
          </select>
        </label>
        <div className="engineeringTargetIdentity" aria-label="Selected Engineering PPU">
          <span className="simulationBadge">{selectedPPU?.provider?.toUpperCase() ?? "—"}</span>
          <b>{facility?.display_name ?? t("engineeringProgramming.noFacility")} / {selectedPPU?.display_name ?? t("engineeringProgramming.noPpu")}</b>
          <small>{ppu?.ppu_id ?? selectedPPU?.ppu_id ?? "—"} · {ppu?.site_count ?? selectedPPU?.site_count ?? 0} Sites · {ppu?.model ?? selectedPPU?.model ?? "—"}</small>
        </div>
      </div>

      {catalog && <div className="engineeringBoundaryNote">
        <b>{t("engineeringProgramming.serverSource")}</b>
        <span>{catalog.facility_count} Facilities · {catalog.ppu_count} PPUs · {catalog.site_count} Sites。{t("engineeringProgramming.serverSourceNote")}</span>
      </div>}

      <section className="selectorPanel engineeringSelectorPanel" aria-label="Engineering Site selection">
        <div className="sectionHeading">
          <div><p className="eyebrow">TARGET SITES</p><h2>{t("engineeringProgramming.siteSelection")}</h2></div>
          <div className="statusSummary"><span>{t("engineeringProgramming.selected")} <b>{selectedSiteIds.length} / {sites.length}</b></span></div>
        </div>
        <div className="channelChecks">
          {sites.map(site => (
            <label key={site.id} className={`${selectedSiteIds.includes(site.id) ? "checked" : ""} ${!site.enabled ? "disabled" : ""}`}>
              <input
                type="checkbox"
                aria-label={`選取 SITE ${site.id}`}
                checked={selectedSiteIds.includes(site.id)}
                disabled={batchRunning || !site.enabled || isRunning(site)}
                onChange={() => toggleSite(site.id)}
              />
              <span>{siteLabel(site.id)}</span>
              <small>{site.enabled ? site.stage.toUpperCase() : "DISABLED"}</small>
            </label>
          ))}
        </div>
      </section>

      <section className="overviewCard" aria-label="Engineering Site status">
        <div className="overviewHead"><div><p className="eyebrow">LIVE PPU STATUS</p><h2>{ppu?.display_name ?? selectedPPU?.display_name ?? t("engineeringProgramming.selectedPpu")}</h2></div><small>REST polling 500 ms</small></div>
        <div className="channelTableWrap">
          <table className="channelTable">
            <thead><tr><th>Site</th><th>{t("engineeringProgramming.targetInterface")}</th><th>{t("engineeringProgramming.operation")}</th><th>{t("engineeringProgramming.state")}</th><th>{t("engineeringProgramming.progress")}</th><th>{t("engineeringProgramming.independent")}</th></tr></thead>
            <tbody>
              {selectedSites.map(site => (
                <tr key={site.id}>
                  <td><b>{siteLabel(site.id)}</b></td>
                  <td><b>{site.target ?? "—"}</b><small>{site.interface ?? "—"}</small></td>
                  <td>{site.operation?.toUpperCase() ?? "—"}{site.error && <small className="errorText">{site.error}</small>}</td>
                  <td><span className={`state ${site.stage}`}>{site.stage.toUpperCase()}</span></td>
                  <td><div className="tableProgress"><div className="track"><i style={{ width: `${site.progress}%` }} /></div><b>{Math.round(site.progress)}%</b></div></td>
                  <td><div className="rowActions">
                    {operationOrder.map(operation => <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`SITE ${site.id} ${t(`operation.${operation}`)}`} title={t(`operation.${operation}`)} disabled={operationDisabled(site, operation)} onClick={() => runSingleSite(site.id, operation)}>{operationCodes[operation]}</button>)}
                    <button className="stop" aria-label={`Cancel SITE ${site.id}`} disabled={!isRunning(site)} onClick={() => void cancelSite(site.id)}>■</button>
                    {site.stage === "success" && site.jobId && site.outputFile && targetApiBase && <a className="rowDownload" aria-label={`Download SITE ${site.id} read file`} href={readDownloadUrl(targetApiBase, site.jobId, site.outputFile)}>↓</a>}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <EngineeringLogPanel logs={logs} onClear={() => setLogs([])} />
    </section>
  );
}
