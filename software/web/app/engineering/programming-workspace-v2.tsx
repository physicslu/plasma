"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { evaluateBatchReadiness } from "../batch-readiness";
import type { DeviceSearchResult } from "../device-catalog-api";
import {
  cachedGatewaySettings,
  getGatewaySettings,
  subscribeGatewaySettings,
  type GatewaySettings,
} from "../gateway-settings-api";
import { useI18n } from "../i18n";
import { BatchSummary } from "../operator-ui/batch-summary";
import { ProgrammingJobPanel } from "../operator-ui/programming-job-panel";
import {
  cancelJob,
  engineeringTargetApiBase,
  getEngineeringTargets,
  getGatewayLiveness,
  getJob,
  getPPUStatus,
  PlasmaApiError,
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
import type { BatchSiteSnapshot } from "../server-batch-api";
import { useWorkspaceSession, type TargetSelection } from "../workspace-session";
import {
  abortEngineeringServerBatch,
  restoreEngineeringServerBatch,
  startEngineeringServerBatch,
  useEngineeringServerBatchState,
} from "./engineering-server-batch";
import "./programming-workspace-base.css";
import EngineeringLogPanel, {
  classifyEngineeringLog,
  engineeringLogCategoryLabel,
  type EngineeringLogCategory,
  type EngineeringLogEntry,
} from "./engineering-log-panel";
import "./programming-workspace-v2.css";

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
type PendingRestore = {
  target: TargetSelection;
  siteIds: number[] | null;
  targetRestored: boolean;
};

type StopPolicy = { kind: "never" } | { kind: "failed_sites"; threshold: number };

const MAX_IMAGE_ASSET_BYTES = 16 * 1024 * 1024;
const MAX_LOG_ENTRIES = 1000;
const POLL_INTERVAL_MS = 500;
const runningStages: Stage[] = ["queued", "erase", "program", "verify", "read"];
const terminalStates = new Set<JobState>(["success", "failed", "error", "cancelled", "timeout", "aborted"]);
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };

class GatewayUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GatewayUnavailableError";
  }
}

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

function targetDeviceLabel(device: DeviceSearchResult | null): string {
  return device?.icpn ?? device?.identifier ?? "—";
}

function resultLabel(stage: Stage): string {
  if (stage === "success") return "PASS";
  if (stage === "faulted" || stage === "failed") return "FAIL";
  if (stage === "error" || stage === "timeout" || stage === "aborted") return "ERROR";
  if (stage === "cancelled") return "CANCELLED";
  if (stage === "stopped") return "STOPPED";
  return "—";
}

function formatElapsedTime(milliseconds: number | null): string {
  if (milliseconds === null || !Number.isFinite(milliseconds) || milliseconds < 0) return "00:00:00";
  const elapsedSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;
  return [hours, minutes, seconds].map(value => String(value).padStart(2, "0")).join(":");
}

function serverBatchElapsedMs(startedAt: string | null, finishedAt: string | null, now: number): number | null {
  if (!startedAt) return null;
  const start = Date.parse(startedAt);
  const end = finishedAt ? Date.parse(finishedAt) : now;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return end - start;
}

function serverSiteStage(site: BatchSiteSnapshot, stopping: boolean): Stage {
  if (site.state === "ready") return stopping ? "stopped" : "idle";
  if (site.state === "running") return site.current_operation ?? "queued";
  return site.state;
}

export default function ProgrammingWorkspaceV2() {
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
  } = useWorkspaceSession();
  const engineeringBatch = useEngineeringServerBatchState();
  const batchSnapshot = engineeringBatch.snapshot;

  const [apiDraft, setApiDraft] = useState(apiBase);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [connectionGeneration, setConnectionGeneration] = useState(0);
  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [ppu, setPPU] = useState<PPUSnapshot | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [targetDevice, setTargetDevice] = useState<DeviceSearchResult | null>(null);
  const [operatorWarning, setOperatorWarning] = useState<string | null>(null);
  const [submittingSiteIds, setSubmittingSiteIds] = useState<number[]>([]);
  const [repeatCount, setRepeatCount] = useState("1");
  const [siteRetryLimit, setSiteRetryLimit] = useState("3");
  const [stopPolicy, setStopPolicy] = useState<StopPolicy>({ kind: "never" });
  const [logs, setLogs] = useState<EngineeringLogEntry[]>([]);
  const [clock, setClock] = useState(() => Date.now());
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [programmingJobCollapsed, setProgrammingJobCollapsed] = useState(false);

  const trackedJobs = useRef<Record<number, string>>({});
  const submissionGenerations = useRef<Record<number, number>>({});
  const configuredGatewayPolicy = useRef<GatewaySettings>(cachedGatewaySettings(apiBase));
  const cancelRequests = useRef<Set<string>>(new Set());
  const logSequence = useRef(0);
  const lastObservedBatchState = useRef<string | null>(null);
  const syncedBatchId = useRef<string | null>(null);
  const initialSelectionKey = selection.facilityId && selection.ppuId
    ? `${selection.facilityId}/${selection.ppuId}`
    : null;
  const siteSelectionTarget = useRef<string | null>(selectedSiteIdsState !== null ? initialSelectionKey : null);
  const pendingRestore = useRef<PendingRestore | null>(null);
  const restartSessionRequested = useRef(false);

  const serverBatchActive = batchSnapshot?.state === "queued"
    || batchSnapshot?.state === "running"
    || batchSnapshot?.state === "stopping";
  const batchRunning = serverBatchActive
    || engineeringBatch.commandState === "submitting"
    || engineeringBatch.commandState === "aborting";
  const batchCancelling = batchSnapshot?.state === "stopping" || engineeringBatch.commandState === "aborting";
  const batchObservationState = engineeringBatch.observationState;

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
  const selectableSiteIds = sites
    .filter(site => site.enabled && !isRunning(site))
    .map(site => site.id);
  const allSelectableSitesSelected = selectableSiteIds.length > 0
    && selectableSiteIds.every(siteId => selectedSiteIds.includes(siteId));
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
    imagePresent: Boolean(imageAsset) || syntheticMockImageAvailable || Boolean(batchSnapshot?.asset),
    imageValid: !imageAsset || imageAsset.size <= MAX_IMAGE_ASSET_BYTES,
    readSelected: selectedOperations.includes("read"),
    readParamsValid: true,
    allSitesExecutable,
    batchRunning: batchRunning && !batchCancelling,
    batchCancelling,
  });
  const noOperationWarning = locale === "zh-TW"
    ? "未選擇任何操作。請至少選擇 Erase、Program、Verify 或 Read 其中一項。"
    : "No operation selected. Select at least one of Erase, Program, Verify, or Read.";
  const dismissWarning = locale === "zh-TW" ? "關閉警告" : "Dismiss warning";
  const syntheticImageLabel = "Mock Synthetic Image";
  const syntheticImageHint = locale === "zh-TW"
    ? "未選 Image 時由 Mock Settings 的 Default Image Size 自動產生 Synthetic Image；手動選檔時以選檔優先。"
    : "Without a selected Image, Mock generates a Synthetic Image from Default Image Size; a selected file takes precedence.";
  const repeatValue = parsePositiveInt(repeatCount);
  const retryValue = parseNonNegativeInt(siteRetryLimit);
  const thresholdValue = stopPolicy.kind === "never" ? null : stopPolicy.threshold;
  const policyValid = repeatValue !== null
    && repeatValue <= 10_000
    && retryValue !== null
    && retryValue <= 20
    && (thresholdValue === null || (thresholdValue >= 1 && thresholdValue <= selectedSiteIds.length));
  const stopPolicyValue = stopPolicy.kind === "never" ? "never" : String(stopPolicy.threshold);

  const previewTotalIc = selectedSiteIds.length * (repeatValue ?? 0);
  const batchManufacturing = useMemo(() => {
    if (!batchSnapshot) return null;
    const pass = batchSnapshot.sites.reduce((total, site) => total + Math.max(0, site.completed_rounds), 0);
    const fail = batchSnapshot.sites.reduce((total, site) => total + Math.max(0, site.final_failures), 0);
    return {
      sites: batchSnapshot.sites.length,
      totalIc: batchSnapshot.sites.length * batchSnapshot.execution_policy.repeat_count,
      pass,
      fail,
    };
  }, [batchSnapshot]);
  const displayedBatch = batchManufacturing ?? {
    sites: selectedSiteIds.length,
    totalIc: previewTotalIc,
    pass: 0,
    fail: 0,
  };
  const completedIc = displayedBatch.pass + displayedBatch.fail;
  const yieldLabel = completedIc > 0
    ? `${((displayedBatch.pass / completedIc) * 100).toFixed(1)}%`
    : "—";
  const displayedTargetDevice = targetDeviceLabel(targetDevice);
  const cycleMs = batchSnapshot
    ? serverBatchElapsedMs(batchSnapshot.started_at, batchSnapshot.finished_at, clock)
    : null;
  const batchTimeLabel = formatElapsedTime(cycleMs);
  const batchKpis = [
    { key: "sites", label: "SITES", value: displayedBatch.sites },
    { key: "total-ic", label: "TOTAL IC", value: displayedBatch.totalIc },
    { key: "processed-ic", label: "PROCESSED IC", value: completedIc },
    { key: "pass", label: "PASS", value: displayedBatch.pass, tone: "pass" as const },
    { key: "fail", label: "FAIL", value: displayedBatch.fail, tone: "fail" as const },
    { key: "yield", label: "YIELD", value: yieldLabel, tone: "info" as const },
    { key: "batch-time", label: "BATCH TIME", value: batchTimeLabel },
  ];
  const batchSitesById = useMemo(
    () => new Map((batchSnapshot?.sites ?? [])
      .filter(site => site.facility_id === selection.facilityId && site.ppu_id === selection.ppuId)
      .map(site => [site.site_id, site] as const)),
    [batchSnapshot, selection.facilityId, selection.ppuId],
  );

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
    setPPU(null);
    setSites([]);
    if (!preserveSiteSelection) {
      siteSelectionTarget.current = null;
      setSelectedSiteIdsState(null);
    }
    setSubmittingSiteIds([]);
  }, [setSelectedSiteIdsState]);

  const switchTarget = useCallback((next: TargetSelection) => {
    pendingRestore.current = null;
    resetTargetRuntime();
    setSelection(next);
    if (next.facilityId && next.ppuId) appendLog(`[TARGET] ${next.facilityId} / ${next.ppuId}`, false, "SYS");
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
    const timer = window.setInterval(() => setClock(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!workspaceHydrated) return;
    queueMicrotask(() => setApiDraft(apiBase));
  }, [apiBase, workspaceHydrated]);

  useEffect(() => {
    if (!workspaceHydrated) return;
    configuredGatewayPolicy.current = cachedGatewaySettings(apiBase);
    let disposed = false;
    const unsubscribe = subscribeGatewaySettings((updatedBase, settings) => {
      if (!disposed && updatedBase === apiBase) configuredGatewayPolicy.current = settings;
    });
    void getGatewaySettings(apiBase)
      .then(settings => {
        if (!disposed) configuredGatewayPolicy.current = settings;
      })
      .catch(() => {
        // Direct Engineering Jobs retain the safe client default until settings are available.
        // Server Batch Runtime freezes its own authoritative Gateway policy at START.
      });
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, [apiBase, workspaceHydrated]);

  useEffect(() => {
    if (!batchSnapshot || syncedBatchId.current === batchSnapshot.batch_id) return;
    syncedBatchId.current = batchSnapshot.batch_id;
    const snapshot = batchSnapshot;
    queueMicrotask(() => {
      const first = snapshot.sites[0];
      if (first) {
        const batchTarget = { facilityId: first.facility_id, ppuId: first.ppu_id };
        if (!sameTarget(selection, batchTarget)) setSelection(batchTarget);
        const ids = snapshot.sites
          .filter(site => site.facility_id === first.facility_id && site.ppu_id === first.ppu_id)
          .map(site => site.site_id)
          .sort((left, right) => left - right);
        siteSelectionTarget.current = `${first.facility_id}/${first.ppu_id}`;
        setSelectedSiteIdsState(ids);
      }
      setSelectedOperations([...snapshot.operations]);
      setRepeatCount(String(snapshot.execution_policy.repeat_count));
      setSiteRetryLimit(String(snapshot.execution_policy.site_retry_limit));
      setStopPolicy(snapshot.execution_policy.failed_site_stop_threshold === null
        ? { kind: "never" }
        : { kind: "failed_sites", threshold: snapshot.execution_policy.failed_site_stop_threshold });
    });
  }, [batchSnapshot, selection, setSelectedOperations, setSelectedSiteIdsState, setSelection]);

  useEffect(() => {
    if (!batchSnapshot) return;
    const marker = `${batchSnapshot.batch_id}:${batchSnapshot.state}`;
    if (lastObservedBatchState.current === marker) return;
    lastObservedBatchState.current = marker;
    const mockRevision = batchSnapshot.mock_runtime?.profile_revision;
    appendLog(
      `[BATCH] ${batchSnapshot.state.toUpperCase()} · ${batchSnapshot.batch_id}${mockRevision ? ` · Mock rev ${mockRevision}` : ""}`,
      batchSnapshot.state === "error",
      "BAT",
    );
  }, [appendLog, batchSnapshot]);

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

        const restoredBatch = await restoreEngineeringServerBatch(apiBase);
        if (cancelled) return;
        if (restoredBatch) {
          const first = restoredBatch.sites[0];
          if (first) {
            setSelection({ facilityId: first.facility_id, ppuId: first.ppu_id });
            setSelectedSiteIdsState(restoredBatch.sites
              .filter(site => site.facility_id === first.facility_id && site.ppu_id === first.ppu_id)
              .map(site => site.site_id)
              .sort((left, right) => left - right));
          }
          appendLog(`[BATCH] RESTORED · ${restoredBatch.batch_id} · ${restoredBatch.state.toUpperCase()}`, false, "BAT");
        } else {
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
        }
        appendLog(`[ENGINEERING] Provider ${next.provider.toUpperCase()} · ${next.facility_count} Facilities · ${next.ppu_count} PPUs · ${next.site_count} Sites`);
      } catch (loadError) {
        restartSessionRequested.current = false;
        if (cancelled) return;
        const message = loadError instanceof Error ? loadError.message : "Engineering target provider unavailable";
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
  }, [apiBase, connectionGeneration, appendLog, ensureEngineeringSession, resetTargetRuntime, restartEngineeringSession, setSelectedSiteIdsState, setSelection, workspaceHydrated]);

  useEffect(() => {
    if (!targetApiBase || !targetSelectionKey) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const submissionSnapshot = { ...submissionGenerations.current };
        const requestTimeoutMs = configuredGatewayPolicy.current.ppu_request_timeout_ms;
        const status = await getPPUStatus(targetApiBase!, requestTimeoutMs);
        if (stopped) return;
        setPPU(status.ppu ?? null);
        const availableIds = new Set(status.sites.map(site => site.site_id));
        Object.keys(trackedJobs.current).forEach(siteId => {
          if (!availableIds.has(Number(siteId))) delete trackedJobs.current[Number(siteId)];
        });
        if (!batchRunning) {
          status.sites.forEach(site => {
            const changed = (submissionGenerations.current[site.site_id] ?? 0)
              !== (submissionSnapshot[site.site_id] ?? 0);
            if (site.current_job_id && !changed) trackedJobs.current[site.site_id] = site.current_job_id;
          });
        }
        setSites(current => status.sites.map(snapshot => (
          siteFromStatus(snapshot, current.find(site => site.id === snapshot.site_id))
        )));
        const enabledIds = status.sites.filter(site => site.enabled).map(site => site.site_id);
        const restore = pendingRestore.current;
        if (!batchRunning && restore?.targetRestored && sameTarget(restore.target, selection)) {
          siteSelectionTarget.current = targetSelectionKey;
          if (restore.siteIds === null) {
            setSelectedSiteIdsState(enabledIds);
          } else {
            const restoredIds = restore.siteIds.filter(id => availableIds.has(id));
            setSelectedSiteIdsState(restoredIds);
            appendLog(`[SITE] RESTORED · ${siteListLabel(restoredIds)}`, false, "SYS");
          }
          pendingRestore.current = null;
        } else if (!batchRunning) {
          setSelectedSiteIdsState(current => {
            if (siteSelectionTarget.current !== targetSelectionKey) {
              siteSelectionTarget.current = targetSelectionKey;
              return enabledIds;
            }
            if (current === null) return enabledIds;
            return current.filter(id => availableIds.has(id));
          });
        }

        const jobIds = batchRunning ? [] : [...new Set(Object.values(trackedJobs.current))];
        const jobs = await Promise.all(jobIds.map(jobId => getJob(targetApiBase!, jobId, requestTimeoutMs)));
        if (stopped) return;
        jobs.forEach(job => {
          if (trackedJobs.current[job.site_id] !== job.job_id) return;
          applyJob(job);
          if (terminalStates.has(job.state)) delete trackedJobs.current[job.site_id];
        });
        setCatalogError(null);
      } catch (pollError) {
        if (!stopped) {
          const message = pollError instanceof Error ? pollError.message : "unknown error";
          setCatalogError(message);
          appendLog(`[TARGET] Status failed · ${selection.facilityId}/${selection.ppuId} · ${message}`, true, "PPU");
        }
      } finally {
        if (!stopped) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [targetApiBase, targetSelectionKey, connectionGeneration, selection, applyJob, appendLog, batchRunning, setSelectedSiteIdsState]);

  function connect(event: FormEvent) {
    event.preventDefault();
    appendLog(`[CONNECTION] CONNECT · ${apiDraft}`, false, "USR");
    if (targetLocked) {
      appendLog("[NET] Gateway change blocked while a target Job or Batch is active", true);
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
    } catch (connectError) {
      appendLog(`[NET] ${connectError instanceof Error ? connectError.message : "Invalid Gateway URL"}`, true);
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

  function selectTargetDevice(device: DeviceSearchResult | null) {
    setTargetDevice(device);
    if (device) appendLog(`[TARGET IC] SELECT · ${device.vendor} / ${targetDeviceLabel(device)}`, false, "USR");
  }

  function applySiteSelection(next: number[]) {
    if (batchRunning) return;
    if (targetSelectionKey) siteSelectionTarget.current = targetSelectionKey;
    setSelectedSiteIdsState(next);
    if (stopPolicy.kind === "failed_sites" && stopPolicy.threshold > next.length) {
      setStopPolicy(next.length > 0 ? { kind: "failed_sites", threshold: next.length } : { kind: "never" });
    }
    appendLog(`[SITE] SELECTION · ${siteListLabel(next)}`, false, "USR");
  }

  function toggleSite(siteId: number) {
    const next = selectedSiteIds.includes(siteId)
      ? selectedSiteIds.filter(id => id !== siteId)
      : [...selectedSiteIds, siteId].sort((left, right) => left - right);
    applySiteSelection(next);
  }

  function toggleAllSites() {
    applySiteSelection(allSelectableSitesSelected ? [] : selectableSiteIds);
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
    if (batchRunning) return;
    setImageAsset(file);
    appendLog(
      file
        ? `[IMG] SELECT · ${file.name} · ${imageAssetSizeLabel(file.size)}`
        : "[IMG] CLEAR",
      false,
      "USR",
    );
  }

  function operationDisabled(site: Site, operation: Operation): boolean {
    if (!targetApiBase || connection !== "online" || !site.enabled || isRunning(site)) return true;
    if (batchRunning) return true;
    if (submittingSiteIds.includes(site.id)) return true;
    if ((operation === "program" || operation === "verify") && !imageAsset && !syntheticMockImageAvailable) return true;
    if ((operation === "program" || operation === "verify") && Boolean(imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES)) return true;
    return false;
  }

  async function runSite(siteId: number, operation: Operation): Promise<JobSnapshot | undefined> {
    if (!targetApiBase || batchRunning) return;
    const site = sites.find(item => item.id === siteId);
    if (!site || operationDisabled(site, operation)) return;
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
        targetDevice: targetDevice ? { vendor: targetDevice.vendor, identifier: targetDevice.identifier } : undefined,
        requestTimeoutMs: configuredGatewayPolicy.current.ppu_request_timeout_ms,
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
    } catch (submitError) {
      if (submitError instanceof PlasmaSubmissionBlockedError) return;
      const message = submitError instanceof Error ? submitError.message : "unknown error";
      appendLog(`[${siteLabel(siteId)}] Submit failed · ${message}`, true);
      setSites(current => current.map(item => item.id === siteId ? {
        ...item,
        stage: "error",
        operation,
        error: message,
      } : item));
    } finally {
      setSubmittingSiteIds(current => current.filter(id => id !== siteId));
    }
  }

  function runSingleSite(siteId: number, operation: Operation) {
    const readDetail = operation === "read" ? " · MAIN FLASH" : "";
    appendLog(`[${siteLabel(siteId)}] EXECUTE ${operation.toUpperCase()}${readDetail}`, false, "USR");
    void runSite(siteId, operation);
  }

  async function withCommunicationRetry<T>(
    label: string,
    policy: GatewaySettings,
    request: () => Promise<T>,
  ): Promise<T> {
    for (let retry = 0; retry <= policy.ppu_retry_count; retry += 1) {
      try {
        const result = await request();
        if (retry > 0) {
          appendLog(`[PPU] CONNECTION RESTORED · ${selection.facilityId}/${selection.ppuId} · ${label}`, false, "PPU");
        }
        return result;
      } catch (error) {
        const transient = error instanceof PlasmaApiError && error.transient;
        if (!transient || retry >= policy.ppu_retry_count) {
          if (transient) {
            try {
              await getGatewayLiveness(apiBase, policy.ppu_request_timeout_ms);
            } catch {
              throw new GatewayUnavailableError(error.message);
            }
          }
          throw error;
        }
        const attempt = retry + 1;
        appendLog(
          `[PPU] RECONNECTING · ${selection.facilityId}/${selection.ppuId} · ${label} · retry ${attempt}/${policy.ppu_retry_count} · ${error.message}`,
          true,
          "PPU",
        );
        await new Promise(resolve => window.setTimeout(resolve, Math.min(2 ** retry, 4) * 1000));
      }
    }
    throw new Error("PPU communication retry loop terminated unexpectedly");
  }

  async function requestCancel(siteId: number, jobId: string): Promise<boolean> {
    if (!targetApiBase || cancelRequests.current.has(jobId) || batchRunning) return false;
    cancelRequests.current.add(jobId);
    const policy = configuredGatewayPolicy.current;
    try {
      await withCommunicationRetry(
        `CANCEL ${jobId}`,
        policy,
        () => cancelJob(targetApiBase, jobId, policy.ppu_request_timeout_ms),
      );
      appendLog(`[${siteLabel(siteId)}] Cancel requested · ${jobId}`);
      return true;
    } catch (cancelError) {
      cancelRequests.current.delete(jobId);
      appendLog(`[${siteLabel(siteId)}] Cancel failed · ${cancelError instanceof Error ? cancelError.message : "unknown error"}`, true);
      return false;
    }
  }

  async function runBatch() {
    if (batchRunning) return;
    if (!batchReadiness.ready) {
      if (batchReadiness.code === "no-op") setOperatorWarning(noOperationWarning);
      appendLog(`[BATCH] BLOCKED · ${batchReadiness.label}`, false, "USR");
      return;
    }
    if (!policyValid || repeatValue === null || retryValue === null || !selection.facilityId || !selection.ppuId) {
      setOperatorWarning("Batch Execution Policy or target is invalid.");
      appendLog("[BATCH] BLOCKED · Batch Execution Policy or target is invalid.", false, "USR");
      return;
    }

    const siteIds = [...selectedSiteIds];
    const operations = operationOrder.filter(operation => selectedOperations.includes(operation));
    const readDetail = operations.includes("read") ? " · read MAIN FLASH" : "";
    setOperatorWarning(null);
    trackedJobs.current = {};
    appendLog(
      `[BATCH] SUBMIT · ${operationListLabel(operations)} · ${siteListLabel(siteIds)} · repeat ${repeatValue} · retry ${retryValue} · threshold ${thresholdValue ?? "off"}${readDetail}`,
      false,
      "USR",
    );

    try {
      const accepted = await startEngineeringServerBatch(apiBase, {
        sessionId: engineeringSessionId,
        targets: [{
          facility_id: selection.facilityId,
          ppu_id: selection.ppuId,
          site_ids: siteIds,
        }],
        operations,
        executionPolicy: {
          repeat_count: repeatValue,
          site_retry_limit: retryValue,
          failed_site_stop_threshold: thresholdValue,
        },
        targetDevice: targetDevice ? { vendor: targetDevice.vendor, identifier: targetDevice.identifier } : null,
        assetFile: imageAsset,
        allowSyntheticMockImage: syntheticMockImageAvailable,
      });
      const mockRevision = accepted.mock_runtime?.profile_revision;
      appendLog(
        `[BATCH] ACCEPTED · ${accepted.batch_id}${mockRevision ? ` · Mock rev ${mockRevision}` : ""}`,
        false,
        "BAT",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Batch submission failed";
      setOperatorWarning(message);
      appendLog(`[BATCH] SUBMISSION ERROR · ${message}`, true, "BAT");
    }
  }

  async function cancelBatch() {
    if (!batchRunning || batchCancelling || !batchSnapshot) return;
    appendLog(`[BATCH] ABORT REQUESTED · ${batchSnapshot.batch_id}`, false, "USR");
    try {
      await abortEngineeringServerBatch(apiBase);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Batch abort failed";
      setOperatorWarning(message);
      appendLog(`[BATCH] ABORT ERROR · ${message}`, true, "BAT");
    }
  }

  async function cancelSite(siteId: number) {
    if (batchRunning) return;
    const site = sites.find(item => item.id === siteId);
    if (!site?.jobId || !isRunning(site)) return;
    appendLog(`[${siteLabel(siteId)}] CANCEL`, false, "USR");
    await requestCancel(siteId, site.jobId);
  }

  const displayedImageName = imageAsset?.name
    ?? batchSnapshot?.asset?.name
    ?? (requiresImage && syntheticMockImageAvailable ? syntheticImageLabel : "Select programming image (.bin)...");

  return (
    <section className="engineeringProgramming engineeringProgrammingV2">
      <main className="productionProgrammingV2">
        <header className="productionProgrammingHeader engineeringProgrammingV2Header">
          <h1>SINGLE PPU PROGRAMMING</h1>
          <form className={`engineeringGateway ${connection}`} onSubmit={connect}>
            <span className="onlineDot" />
            <input aria-label="Engineering Gateway URL" value={apiDraft} disabled={targetLocked} onChange={event => setApiDraft(event.target.value)} />
            <button type="submit" disabled={targetLocked}>Connect</button>
            <b>EMode</b>
          </form>
        </header>

        <BatchSummary
          items={batchKpis}
          ariaLabel="Engineering Batch Summary"
          title="BATCH SUMMARY"
          meta={`${batchSnapshot ? "Current Batch" : "Batch Preview"} · ${displayedBatch.sites} Sites · ${displayedBatch.totalIc} ICs`}
        />

        <div className="productionProgrammingWorkflow">
          <section className={`productionProgrammingCard targetingCard ${setupCollapsed ? "is-collapsed" : ""}`}>
            <header>
              SYSTEM SETUP &amp; TARGETING
              <button
                type="button"
                className="engineeringPanelToggle"
                aria-label={`${setupCollapsed ? "Expand" : "Collapse"} System Setup`}
                aria-expanded={!setupCollapsed}
                onClick={() => setSetupCollapsed(current => !current)}
              >{setupCollapsed ? "展開⌄" : "收合⌃"}</button>
            </header>
            <div className="cardBody" hidden={setupCollapsed}>
              <h2>SERVER TOPOLOGY</h2>
              <label className="workflowField">
                <span>Select Facility:</span>
                <select
                  aria-label="Engineering Facility"
                  value={selection.facilityId}
                  disabled={!catalog || targetLocked}
                  onChange={event => selectFacility(event.target.value)}
                >
                  {(catalog?.facilities ?? []).map(item => <option key={item.facility_id} value={item.facility_id}>{item.display_name}</option>)}
                </select>
              </label>
              <label className="workflowField">
                <span>Select PPU:</span>
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
              <div className="topologyFoot" aria-label="Selected Engineering PPU">
                <b>{facility?.display_name ?? "No Facility"} / {selectedPPU?.display_name ?? "No PPU"}</b>
                {' · '}{ppu?.ppu_id ?? selectedPPU?.ppu_id ?? "—"}{' · '}{ppu?.site_count ?? selectedPPU?.site_count ?? 0} Sites
                {' · '}System Topology: {catalog?.facility_count ?? 0} Facilities | {catalog?.ppu_count ?? 0} PPUs | {catalog?.site_count ?? 0} Sites
              </div>
            </div>
          </section>

          <div className="productionProgrammingRight">
            <ProgrammingJobPanel
              mode="engineering"
              title="PROGRAMMING JOB"
              collapsed={programmingJobCollapsed}
              onToggleCollapsed={() => setProgrammingJobCollapsed(current => !current)}
              expandLabel={locale === "zh-TW" ? "展開" : "Show"}
              collapseLabel={locale === "zh-TW" ? "收合" : "Hide"}
              apiBase={apiBase}
              targetDevice={targetDevice}
              onTargetChange={selectTargetDevice}
              targetDisabled={targetLocked}
              targetPlaceholder="Search ICPN / IC identifier..."
              targetLabel="Target IC"
              imageLabel="Programming Image"
              image={{
                name: displayedImageName,
                title: displayedImageName,
                source: imageAsset ? "user" : batchSnapshot?.asset ? "batch_snapshot" : requiresImage && syntheticMockImageAvailable ? "mock_synthetic" : "none",
                hint: syntheticMockImageAvailable ? syntheticImageHint : "Binary Programming Image (.bin).",
                browseLabel: "Browse...",
                browseDisabled: targetLocked,
                inputDisabled: targetLocked,
                inputAriaLabel: "Engineering Programming Image Asset file",
                onFileChange: file => selectImageAsset(file),
              }}
              operationsLabel="Operations"
              operations={operationOrder.map(operation => ({
                key: operation,
                code: operationCodes[operation],
                label: t(`operation.${operation}`),
                checked: selectedOperations.includes(operation),
                disabled: batchRunning,
                ariaLabel: `Engineering batch ${operation}`,
                onChange: () => toggleOperation(operation),
              }))}
              policyLabel="Batch Policy"
              policy={{
                repeatLabel: "Repeat",
                repeatValue: repeatCount,
                repeatDisabled: batchRunning,
                repeatAriaLabel: "Repeat Count",
                onRepeatChange: setRepeatCount,
                retryLabel: "Retry",
                retryValue: siteRetryLimit,
                retryDisabled: batchRunning,
                retryAriaLabel: "Site Retry Limit",
                onRetryChange: setSiteRetryLimit,
                stopLabel: "Stop Policy",
                stopValue: stopPolicyValue,
                stopDisabled: batchRunning,
                stopAriaLabel: "Engineering Stop Policy",
                stopOptions: [
                  { value: "never", label: "Never" },
                  ...selectedSiteIds.map((_, index) => ({ value: String(index + 1), label: `${index + 1} Fail` })),
                ],
                onStopChange: value => setStopPolicy(value === "never" ? { kind: "never" } : { kind: "failed_sites", threshold: Number(value) }),
              }}
              startLabel="START PROGRAMMING"
              startDisabled={!batchReadiness.ready || !policyValid}
              onStart={runBatch}
              statusLabel="BATCH STATUS"
              statusValue={batchRunning && batchObservationState === "reconnecting" ? "RECONNECTING" : batchReadiness.label}
              statusClassName={`readiness-${batchReadiness.code}`}
              abortLabel="ABORT"
              abortDisabled={!batchRunning || batchCancelling || !batchSnapshot}
              onAbort={cancelBatch}
            />

            {operatorWarning && <div className="warning engineeringOperationWarning" role="alert"><span>{operatorWarning}</span><button type="button" aria-label={dismissWarning} onClick={() => setOperatorWarning(null)}>×</button></div>}
            {engineeringBatch.error && batchObservationState === "reconnecting" && <div className="warning engineeringOperationWarning" role="status">{engineeringBatch.error}</div>}
            {imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES && <div className="warning">{t("engineeringProgramming.imageAssetTooLarge")}</div>}
          </div>
        </div>

        {catalogError && <div className="engineeringBoundaryNote warning"><b>{t("engineeringProgramming.providerOffline")}</b><span>{catalogError}</span></div>}

        <section className="productionProgrammingCard liveSiteStatus overviewCard" aria-label="Engineering Site status">
          <header>
            <span>LIVE SITE STATUS</span>
            <small>{ppu?.display_name ?? selectedPPU?.display_name ?? "Selected PPU"} · {sites.length} Sites · Batch selected {selectedSiteIds.length} · REST polling 500 ms</small>
          </header>
          <div className="channelTableWrap engineeringV2TableWrap" role="region" aria-label="Engineering Site selection">
            <table className="channelTable">
              <thead>
                <tr>
                  <th className="engineeringBatchSelectHead">
                    <label>
                      <input
                        type="checkbox"
                        aria-label="Select all Engineering batch Sites"
                        checked={allSelectableSitesSelected}
                        disabled={batchRunning || selectableSiteIds.length === 0}
                        onChange={toggleAllSites}
                      />
                      <span>BATCH</span>
                    </label>
                  </th>
                  <th>SITE</th><th>TARGET IC</th><th>STATE</th><th>PROGRESS</th><th>RESULT</th><th>OPERATIONS (E/P/V/R)</th>
                </tr>
              </thead>
              <tbody className="targetSitesSection">
                {sites.map(site => {
                  const batchSite = batchSitesById.get(site.id);
                  const displayStage = batchSite ? serverSiteStage(batchSite, batchSnapshot?.state === "stopping") : site.stage;
                  const selectedForBatch = selectedSiteIds.includes(site.id);
                  const progress = batchSite?.progress_percent ?? site.progress;
                  const error = batchSite?.error?.message ?? site.error;
                  const displayState = batchSite
                    ? batchSnapshot?.state === "stopping" && batchSite.state === "running" ? "CANCELLING" : batchSite.state.toUpperCase()
                    : site.stage.toUpperCase();
                  return (
                    <tr key={site.id} data-batch-selected={selectedForBatch ? "true" : "false"} data-site-enabled={site.enabled ? "true" : "false"}>
                      <td className="engineeringBatchSelectCell">
                        <input
                          type="checkbox"
                          aria-label={`Batch select SITE ${site.id}`}
                          checked={selectedForBatch}
                          disabled={batchRunning || !site.enabled || isRunning(site)}
                          onChange={() => toggleSite(site.id)}
                        />
                      </td>
                      <td><b>{siteLabel(site.id)}</b></td>
                      <td><b>{displayedTargetDevice !== "—" ? displayedTargetDevice : (site.target ?? "—")}</b><small>{site.interface ?? "—"}</small></td>
                      <td><span className={`state ${displayStage}`}>{site.enabled ? displayState : "DISABLED"}</span>{error && <small className="errorText">{error}</small>}</td>
                      <td><div className="tableProgress"><div className="track"><i style={{ width: `${progress}%` }} /></div><b>{Math.round(progress)}%</b></div></td>
                      <td><b className="engineeringResult" data-result={resultLabel(displayStage)}>{resultLabel(displayStage)}</b></td>
                      <td><div className="rowActions engineeringV2Actions">
                        {operationOrder.map(operation => <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`SITE ${site.id} ${t(`operation.${operation}`)}`} title={t(`operation.${operation}`)} disabled={operationDisabled(site, operation)} onClick={() => runSingleSite(site.id, operation)}>{operationCodes[operation]}</button>)}
                        <button className="stop" aria-label={`Cancel SITE ${site.id}`} disabled={batchRunning || !isRunning(site)} onClick={() => void cancelSite(site.id)}>■</button>
                        {site.stage === "success" && site.jobId && site.outputFile && targetApiBase && <a className="rowDownload" aria-label={`Download SITE ${site.id} read file`} href={readDownloadUrl(targetApiBase, site.jobId, site.outputFile)}>↓</a>}
                      </div></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <EngineeringLogPanel logs={logs} onClear={() => setLogs([])} />
      </main>
    </section>
  );
}
