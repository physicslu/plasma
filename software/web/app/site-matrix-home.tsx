"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { BatchLifecycle } from "./batch-lifecycle";
import {
  cancelJob,
  DEFAULT_API_BASE,
  getJob,
  getPPUStatus,
  normalizeApiBase,
  PlasmaSubmissionBlockedError,
  readDownloadUrl,
  startJob,
} from "./plasma-api";
import type {
  JobSnapshot,
  JobState,
  Operation,
  PPUSnapshot,
  SiteSnapshot,
} from "./plasma-api";

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
  | "timeout"
  | "aborted";
type Site = {
  id: number;
  enabled: boolean;
  stage: Stage;
  progress: number;
  stageProgress: number;
  operation?: Operation;
  jobId?: string;
  file?: string;
  target?: string;
  interface?: string;
  error?: string;
  outputFile?: string;
};
type Theme = "dark" | "light";
type ConnectionState = "connecting" | "online" | "offline";
type BatchSiteState = "running" | "cancelling" | "success" | "cancelled" | "failed";
type LogLevel = "info" | "error";
type LogEntry = { id: number; text: string; level: LogLevel };

const MAX_IMAGE_ASSET_BYTES = 16 * 1024 * 1024;
const BATCH_JOB_POLL_INTERVAL_MS = 500;
const BATCH_JOB_POLL_ATTEMPTS = 120;
const runningStages: Stage[] = ["queued", "erase", "program", "verify", "read"];
const failedStages: Stage[] = ["cancelled", "failed", "timeout", "aborted"];
const terminalJobStates = new Set<JobState>(["success", "failed", "cancelled", "timeout", "aborted"]);
const stageLabels: Record<Stage, string> = {
  idle: "待命",
  queued: "排隊中",
  erase: "擦除中",
  program: "燒錄中",
  verify: "驗證中",
  read: "讀取中",
  success: "成功",
  cancelled: "已取消",
  failed: "失敗",
  timeout: "逾時",
  aborted: "已中止",
};
const logStageLabels: Record<Stage, string> = {
  idle: "IDLE",
  queued: "QUEUED",
  erase: "ERASING",
  program: "PROGRAMMING",
  verify: "VERIFYING",
  read: "READING",
  success: "SUCCESS",
  cancelled: "CANCELLED",
  failed: "FAILED",
  timeout: "TIMEOUT",
  aborted: "ABORTED",
};
const batchStateLabels: Record<BatchSiteState, string> = {
  running: "執行中",
  cancelling: "取消中",
  success: "完成",
  cancelled: "已取消",
  failed: "失敗",
};
const operationLabels: Record<Operation, string> = {
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  read: "讀取",
};
const operationSymbols: Record<Operation, string> = {
  erase: "擦",
  program: "燒",
  verify: "驗",
  read: "讀",
};
const operationOrder = Object.keys(operationLabels) as Operation[];

function isRunning(site: Site): boolean {
  return runningStages.includes(site.stage);
}

function uiStage(job: JobSnapshot): Stage {
  if (job.state === "running") {
    if (job.stage === "erase" || job.stage === "program" || job.stage === "verify" || job.stage?.startsWith("read_")) {
      return job.stage.startsWith("read_") ? "read" : job.stage;
    }
    return "queued";
  }
  if (job.state === "queued") return "queued";
  return job.state;
}

function siteFromStatus(backend: SiteSnapshot, existing?: Site): Site {
  return {
    id: backend.site_id,
    enabled: backend.enabled,
    stage: existing?.stage ?? "idle",
    progress: existing?.progress ?? 0,
    stageProgress: existing?.stageProgress ?? 0,
    operation: existing?.operation,
    jobId: backend.current_job_id ?? existing?.jobId,
    file: existing?.file,
    target: backend.target ?? undefined,
    interface: backend.interface ?? undefined,
    error: existing?.error,
    outputFile: existing?.outputFile,
  };
}

export default function Home() {
  const [sites, setSites] = useState<Site[]>([]);
  const [visibleSiteIds, setVisibleSiteIds] = useState<number[]>([]);
  const [ppu, setPPU] = useState<PPUSnapshot | null>(null);
  const [imageAsset, setImageAsset] = useState<File | null>(null);
  const [readOffset, setReadOffset] = useState("0");
  const [readLength, setReadLength] = useState("256");
  const [selectedBatchOperations, setSelectedBatchOperations] = useState<Operation[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([{ id: 0, text: "[SYSTEM] Plasma Web Console ready", level: "info" }]);
  const [detailsSiteId, setDetailsSiteId] = useState<number | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_BASE);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [submittingSiteIds, setSubmittingSiteIds] = useState<number[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchCancelling, setBatchCancelling] = useState(false);
  const [batchSiteStates, setBatchSiteStates] = useState<Record<number, BatchSiteState>>({});
  const trackedJobs = useRef<Record<number, string>>({});
  const submissionGenerations = useRef<Record<number, number>>({});
  const transitionKeys = useRef<Record<string, string>>({});
  const connectionRef = useRef<ConnectionState>("connecting");
  const batchLifecycle = useRef<BatchLifecycle | null>(null);
  const cancelRequests = useRef<Set<string>>(new Set());
  const logSequence = useRef(0);

  const visibleSites = sites.filter(site => visibleSiteIds.includes(site.id));
  const enabledCount = sites.filter(site => site.enabled).length;
  const disabledCount = sites.length - enabledCount;
  const detailsSite = detailsSiteId === null
    ? undefined
    : sites.find(site => site.id === detailsSiteId);
  const detailsBatchState = detailsSiteId === null ? undefined : batchSiteStates[detailsSiteId];
  const readRangeValid = Number.isInteger(Number(readOffset))
    && Number(readOffset) >= 0
    && Number.isInteger(Number(readLength))
    && Number(readLength) > 0;

  const statusCounts = useMemo(() => visibleSites.reduce((counts, site) => {
    const batchState = batchSiteStates[site.id];
    if (!site.enabled) counts.disabled += 1;
    else if (batchState === "cancelling" || batchState === "cancelled") counts.cancelled += 1;
    else if (batchState === "running") counts.busy += 1;
    else if (batchState === "success") counts.success += 1;
    else if (batchState === "failed") counts.failed += 1;
    else if (submittingSiteIds.includes(site.id) || isRunning(site)) counts.busy += 1;
    else if (site.stage === "success") counts.success += 1;
    else if (failedStages.includes(site.stage)) counts.failed += 1;
    else counts.idle += 1;
    return counts;
  }, { idle: 0, busy: 0, success: 0, failed: 0, cancelled: 0, disabled: 0 }), [batchSiteStates, submittingSiteIds, visibleSites]);

  const appendLog = useCallback((message: string, level: LogLevel = "info") => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    const prefix = level === "error" ? "[ERROR] " : "";
    const entry: LogEntry = { id: ++logSequence.current, text: `${time}  ${prefix}${message}`, level };
    setLogs(items => [...items.slice(-80), entry]);
  }, []);

  const applyJob = useCallback((job: JobSnapshot) => {
    const stage = uiStage(job);
    const error = job.result?.error?.message;
    const outputFile = job.result?.output_files?.[0]?.split(/[\\/]/).pop();
    setSites(items => items.map(site => site.id === job.site_id ? {
      ...site,
      stage,
      operation: job.operation,
      progress: Number(job.progress_percent ?? 0),
      stageProgress: Number(job.stage_progress_percent ?? 0),
      jobId: job.job_id,
      error,
      outputFile,
    } : site));

    const transitionKey = `${job.state}:${job.stage ?? "-"}`;
    if (transitionKeys.current[job.job_id] !== transitionKey) {
      transitionKeys.current[job.job_id] = transitionKey;
      const level: LogLevel = error || stage === "failed" || stage === "timeout" || stage === "aborted" ? "error" : "info";
      appendLog(
        `[SITE ${job.site_id}] ${job.job_id} · ${logStageLabels[stage]}` +
        (error ? ` · ${error}` : ""),
        level,
      );
    }
  }, [appendLog]);

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("plasma-theme");
    const savedApi = window.localStorage.getItem("plasma-api-base");
    const restore = window.requestAnimationFrame(() => {
      if (savedTheme === "light" || savedTheme === "dark") setTheme(savedTheme);
      if (savedApi) {
        try {
          const normalized = normalizeApiBase(savedApi);
          connectionRef.current = "connecting";
          setConnection("connecting");
          setApiDraft(normalized);
          setApiBase(normalized);
        } catch {
          window.localStorage.removeItem("plasma-api-base");
        }
      }
    });
    return () => window.cancelAnimationFrame(restore);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("plasma-theme", theme);
  }, [theme]);

  useEffect(() => {
    let stopped = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const submissionSnapshot = { ...submissionGenerations.current };
        const status = await getPPUStatus(apiBase);
        if (stopped) return;
        setPPU(status.ppu ?? null);

        const availableSiteIds = new Set(status.sites.map(site => site.site_id));
        Object.keys(trackedJobs.current).forEach(siteId => {
          if (!availableSiteIds.has(Number(siteId))) delete trackedJobs.current[Number(siteId)];
        });
        status.sites.forEach(site => {
          const submissionChanged = (submissionGenerations.current[site.site_id] ?? 0)
            !== (submissionSnapshot[site.site_id] ?? 0);
          if (site.current_job_id && !submissionChanged) {
            trackedJobs.current[site.site_id] = site.current_job_id;
          }
        });

        setSites(current => status.sites.map(backend => (
          siteFromStatus(backend, current.find(site => site.id === backend.site_id))
        )));
        setVisibleSiteIds(current => {
          const retained = current.filter(siteId => availableSiteIds.has(siteId));
          if (retained.length > 0) return retained;
          const enabledSiteIds = status.sites
            .filter(site => site.enabled)
            .map(site => site.site_id);
          if (enabledSiteIds.length > 0) return enabledSiteIds;
          return status.sites.length > 0 ? [status.sites[0].site_id] : [];
        });

        const jobIds = [...new Set(Object.values(trackedJobs.current))];
        const jobs = await Promise.all(jobIds.map(jobId => getJob(apiBase, jobId)));
        if (stopped) return;
        jobs.forEach(job => {
          if (trackedJobs.current[job.site_id] !== job.job_id) return;
          applyJob(job);
          if (terminalJobStates.has(job.state) && trackedJobs.current[job.site_id] === job.job_id) {
            delete trackedJobs.current[job.site_id];
          }
        });
        if (connectionRef.current !== "online") {
          connectionRef.current = "online";
          setConnection("online");
          appendLog(`[NET] Plasma Web REST Gateway connected · ${apiBase}`);
        }
      } catch (error) {
        if (stopped) return;
        if (connectionRef.current !== "offline") {
          connectionRef.current = "offline";
          setConnection("offline");
          appendLog(`[NET] Plasma Web REST Gateway offline · ${apiBase} · ${error instanceof Error ? error.message : "connection failed"}`, "error");
        }
      } finally {
        if (!stopped) pollTimer = window.setTimeout(poll, 500);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [apiBase, appendLog, applyJob]);

  function connect(event: FormEvent) {
    event.preventDefault();
    try {
      const normalized = normalizeApiBase(apiDraft);
      window.localStorage.setItem("plasma-api-base", normalized);
      setApiDraft(normalized);
      connectionRef.current = "connecting";
      setConnection("connecting");
      setApiBase(normalized);
    } catch (error) {
      appendLog(`[NET] Plasma Web REST Gateway rejected · ${apiDraft.trim() || "(empty)"} · ${error instanceof Error ? error.message : "Invalid API URL"}`, "error");
    }
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

  function siteDisplayState(site: Site): { state: Stage | "submitting"; label: string } {
    const batchState = batchSiteStates[site.id];
    const submitting = submittingSiteIds.includes(site.id);
    if (!site.enabled) return { state: "idle", label: "停用" };
    if (batchState === "cancelling") return { state: "cancelled", label: "批次取消中" };
    if (batchState === "cancelled") return { state: "cancelled", label: "批次已取消" };
    if (batchState === "failed") return { state: "failed", label: "批次失敗" };
    if (batchState === "success") return { state: "success", label: "批次完成" };
    if (submitting) return { state: "submitting", label: "提交中" };
    if (batchState === "running" && site.stage === "success") return { state: "queued", label: "批次進行中" };
    return { state: site.stage, label: stageLabels[site.stage] };
  }

  function toggleSite(siteId: number) {
    const site = sites.find(item => item.id === siteId);
    if (!site || batchRunning || isRunning(site) || submittingSiteIds.includes(siteId)) return;
    setVisibleSiteIds(current => {
      if (!current.includes(siteId)) return [...current, siteId].sort((left, right) => left - right);
      if (current.length === 1) {
        appendLog("[UI] At least one site must remain visible");
        return current;
      }
      return current.filter(id => id !== siteId);
    });
  }

  function operationDisabled(site: Site, operation: Operation, forBatch = false): boolean {
    if ((!forBatch && batchRunning) || connection !== "online" || !site.enabled || isRunning(site)) return true;
    if (submittingSiteIds.includes(site.id)) return true;
    if ((operation === "program" || operation === "verify") && !imageAsset) return true;
    if ((operation === "program" || operation === "verify") && imageAsset.size > MAX_IMAGE_ASSET_BYTES) return true;
    if (operation === "read" && !readRangeValid) return true;
    return false;
  }

  function batchDisabled(operation: Operation): boolean {
    return visibleSites.length === 0 || visibleSites.some(site => operationDisabled(site, operation));
  }

  function toggleBatchOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedBatchOperations(current => {
      if (!current.includes(operation)) {
        return operationOrder.filter(item => current.includes(item) || item === operation);
      }
      return current.filter(item => item !== operation);
    });
  }

  async function runSite(
    siteId: number,
    operation: Operation,
    forBatch = false,
    submissionGuard?: () => boolean,
  ): Promise<JobSnapshot | undefined> {
    const site = sites.find(item => item.id === siteId);
    if (!site || operationDisabled(site, operation, forBatch)) return;
    if (imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES) {
      appendLog(`[SITE ${siteId}] Programming Image Asset exceeds the 16 MiB limit`, "error");
      return;
    }

    if (!forBatch) clearBatchSiteState(siteId);
    submissionGenerations.current[siteId] = (submissionGenerations.current[siteId] ?? 0) + 1;
    setSubmittingSiteIds(current => current.includes(siteId) ? current : [...current, siteId]);
    try {
      const job = await startJob(apiBase, {
        siteId,
        operation,
        assetFile: operation === "erase" || operation === "read" ? null : imageAsset,
        offset: operation === "read" ? Number(readOffset) : undefined,
        length: operation === "read" ? Number(readLength) : undefined,
        submissionGuard,
      });
      trackedJobs.current[siteId] = job.job_id;
      setSites(items => items.map(item => item.id === siteId ? {
        ...item,
        stage: "queued",
        operation,
        progress: 0,
        stageProgress: 0,
        jobId: job.job_id,
        file: imageAsset?.name,
        error: undefined,
        outputFile: undefined,
      } : item));
      appendLog(`[SITE ${siteId}] ${job.job_id} accepted by Plasma · ${operation.toUpperCase()}`);
      return job;
    } catch (error) {
      if (error instanceof PlasmaSubmissionBlockedError) return;
      appendLog(`[SITE ${siteId}] Submit failed · ${error instanceof Error ? error.message : "unknown error"}`, "error");
      setSites(items => items.map(item => item.id === siteId ? {
        ...item,
        stage: "failed",
        operation,
        error: error instanceof Error ? error.message : "unknown error",
      } : item));
    } finally {
      setSubmittingSiteIds(current => current.filter(id => id !== siteId));
    }
  }

  async function waitForTerminalJob(job: JobSnapshot): Promise<JobSnapshot> {
    for (let attempt = 0; attempt < BATCH_JOB_POLL_ATTEMPTS; attempt += 1) {
      const current = await getJob(apiBase, job.job_id);
      applyJob(current);
      if (terminalJobStates.has(current.state)) return current;
      await new Promise(resolve => window.setTimeout(resolve, BATCH_JOB_POLL_INTERVAL_MS));
    }
    throw new Error(`${job.job_id} timed out waiting for completion`);
  }

  async function requestJobCancel(siteId: number, jobId: string, fromBatch: boolean) {
    if (cancelRequests.current.has(jobId)) return;
    cancelRequests.current.add(jobId);
    try {
      await cancelJob(apiBase, jobId);
      appendLog(`[SITE ${siteId}] ${fromBatch ? "Batch cancel" : "Cancel"} requested · waiting for safe shutdown`);
    } catch (error) {
      cancelRequests.current.delete(jobId);
      appendLog(`[SITE ${siteId}] Cancel failed · ${error instanceof Error ? error.message : "unknown error"}`, "error");
    }
  }

  async function runBatch(operations: Operation[]) {
    if (batchRunning || operations.length === 0 || operations.some(batchDisabled)) return;
    const batchOperations = [...operations];
    const batchSiteIds = [...visibleSiteIds];
    const lifecycle = new BatchLifecycle(batchSiteIds);
    batchLifecycle.current = lifecycle;
    setBatchSiteStates(batchSiteIds.reduce<Record<number, BatchSiteState>>((states, siteId) => {
      states[siteId] = "running";
      return states;
    }, {}));
    setBatchCancelling(false);
    setBatchRunning(true);
    appendLog(`[BATCH] START ${batchOperations.map(operation => operation.toUpperCase()).join(" → ")} · ${batchSiteIds.map(id => `SITE ${id}`).join(", ")}`);
    try {
      const outcomes = await Promise.all(batchSiteIds.map(async siteId => {
        const stopBeforeDispatch = (operation: Operation) => {
          lifecycle.finish(siteId);
          setBatchSiteState(siteId, "cancelled");
          appendLog(`[SITE ${siteId}] Batch stopped · CANCEL REQUESTED · before ${operation.toUpperCase()} dispatch`);
          return { siteId, state: "cancelled" as const };
        };

        for (const operation of batchOperations) {
          if (!lifecycle.prepare(siteId, operation)) return stopBeforeDispatch(operation);

          appendLog(`[SITE ${siteId}] Batch ${operation.toUpperCase()}`);
          await new Promise(resolve => window.setTimeout(resolve, 0));
          if (!lifecycle.beginSubmit(siteId)) return stopBeforeDispatch(operation);

          const job = await runSite(siteId, operation, true, () => lifecycle.canDispatch(siteId));
          if (!job) {
            if (lifecycle.isCancelRequested(siteId)) return stopBeforeDispatch(operation);
            lifecycle.finish(siteId);
            setBatchSiteState(siteId, "failed");
            return { siteId, state: "failed" as const };
          }

          const cancelAfterAccept = lifecycle.accepted(siteId, job.job_id);
          if (cancelAfterAccept) {
            await requestJobCancel(siteId, job.job_id, true);
          }

          try {
            const finalJob = await waitForTerminalJob(job);
            lifecycle.finish(siteId);

            const cancelWasRequested = lifecycle.isCancelRequested(siteId) || cancelRequests.current.has(job.job_id);
            if (cancelWasRequested) {
              setBatchSiteState(siteId, "cancelled");
              appendLog(`[SITE ${siteId}] Batch stopped · CANCEL REQUESTED · last job ${finalJob.state.toUpperCase()}`);
              return { siteId, state: "cancelled" as const };
            }
            if (finalJob.state === "cancelled") {
              setBatchSiteState(siteId, "cancelled");
              appendLog(`[SITE ${siteId}] Batch stopped · CANCELLED`);
              return { siteId, state: "cancelled" as const };
            }
            if (finalJob.state !== "success") {
              setBatchSiteState(siteId, "failed");
              appendLog(`[SITE ${siteId}] Batch stopped · ${finalJob.state.toUpperCase()}`, "error");
              return { siteId, state: "failed" as const };
            }
          } catch (error) {
            lifecycle.finish(siteId);
            const cancelWasRequested = lifecycle.isCancelRequested(siteId) || cancelRequests.current.has(job.job_id);
            const state = cancelWasRequested ? "cancelled" : "failed";
            setBatchSiteState(siteId, state);
            appendLog(`[SITE ${siteId}] Batch polling failed · ${error instanceof Error ? error.message : "unknown error"}`, "error");
            return { siteId, state };
          }
        }
        lifecycle.finish(siteId);
        setBatchSiteState(siteId, "success");
        appendLog(`[SITE ${siteId}] Batch complete`);
        return { siteId, state: "success" as const };
      }));
      const successfulSiteIds = outcomes.filter(outcome => outcome.state === "success").map(outcome => outcome.siteId);
      const cancelledSiteIds = outcomes.filter(outcome => outcome.state === "cancelled").map(outcome => outcome.siteId);
      const failedSiteIds = outcomes.filter(outcome => outcome.state === "failed").map(outcome => outcome.siteId);
      const summary = `success: ${successfulSiteIds.length ? successfulSiteIds.map(id => `SITE ${id}`).join(", ") : "none"}`
        + (cancelledSiteIds.length ? ` · cancelled: ${cancelledSiteIds.map(id => `SITE ${id}`).join(", ")}` : "")
        + (failedSiteIds.length ? ` · failed: ${failedSiteIds.map(id => `SITE ${id}`).join(", ")}` : "");
      const batchOutcome = failedSiteIds.length
        ? "FAILED"
        : lifecycle.cancelRequested
          ? "CANCELLED"
          : cancelledSiteIds.length
            ? "PARTIAL"
            : "COMPLETE";
      appendLog(`[BATCH] ${batchOutcome} · ${summary}`, failedSiteIds.length ? "error" : "info");
    } finally {
      if (batchLifecycle.current === lifecycle) batchLifecycle.current = null;
      setBatchRunning(false);
      setBatchCancelling(false);
    }
  }

  async function cancelBatch() {
    if (!batchRunning || batchCancelling) return;
    const lifecycle = batchLifecycle.current;
    if (!lifecycle) return;
    const { submittingSites, activeJobs } = lifecycle.cancel();
    setBatchCancelling(true);
    setBatchSiteStates(current => Object.fromEntries(
      Object.entries(current).map(([siteId, state]) => [siteId, state === "running" ? "cancelling" : state]),
    ) as Record<number, BatchSiteState>);
    appendLog(`[BATCH] CANCEL requested · submitting: ${submittingSites.length} · active jobs: ${activeJobs.length}`);
    await Promise.all(activeJobs.map(([siteId, jobId]) => requestJobCancel(siteId, jobId, true)));
  }

  async function cancel(siteId: number) {
    const site = sites.find(item => item.id === siteId);
    if (!site || !site.jobId || !isRunning(site)) return;
    if (batchRunning && batchSiteStates[siteId] === "running") {
      const lifecycle = batchLifecycle.current;
      if (lifecycle) {
        const activeJobId = lifecycle.cancelSite(siteId);
        setBatchSiteState(siteId, "cancelling");
        if (!activeJobId) {
          appendLog(`[SITE ${siteId}] Cancel requested · next batch operation suppressed`);
          return;
        }
        await requestJobCancel(siteId, activeJobId, false);
        return;
      }
      setBatchSiteState(siteId, "cancelling");
    }
    await requestJobCancel(siteId, site.jobId, false);
  }

  const batchTargetText = visibleSiteIds.length
    ? visibleSiteIds.map(id => `SITE ${id}`).join("、")
    : "—";

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brandmark">P</span><div><b>PLASMA</b><small>PPU CONTROL</small></div></div>
        <div className="topActions">
          <div className="themeSwitch" role="group" aria-label="介面主題">
            <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} aria-pressed={theme === "dark"}>深色</button>
            <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} aria-pressed={theme === "light"}>淺色</button>
          </div>
          <form className={`connection ${connection}`} onSubmit={connect}>
            <span className="pulse"/><div><b>Plasma Web REST Gateway</b><input aria-label="Plasma Web REST Gateway URL" value={apiDraft} onChange={event => setApiDraft(event.target.value)}/></div><button type="submit">連線</button>
          </form>
        </div>
      </header>

      <section className="console overviewConsole">
        <div className="pageHeading">
          <div>
            <p className="eyebrow">SITE MATRIX</p>
            <h1>Programming Site 工作總覽</h1>
            {ppu && <div className="statusSummary" aria-label="PPU identity">
              <span>Facility <b>{ppu.facility_id}</b></span>
              <span>PPU <b>{ppu.ppu_id}</b></span>
              <span>Model <b>{ppu.model}</b></span>
            </div>}
          </div>
          <div className={`gatewayHealth ${connection}`}><span className="pulse"/><div><small>Plasma Web REST Gateway</small><b>{connection === "online" ? "Online" : connection === "connecting" ? "Connecting" : "Offline"}</b></div><em>{enabledCount}/{sites.length} Enabled</em></div>
        </div>

        <section className="selectorPanel" aria-labelledby="site-selector-title">
          <div className="sectionHeading">
            <div><p className="eyebrow">DISPLAY SITES</p><h2 id="site-selector-title">顯示與批次操作 Site</h2></div>
            <div className="statusSummary" aria-label="Site 配置摘要"><span>顯示 <b>{visibleSiteIds.length} / {sites.length}</b></span><span>停用 <b>{disabledCount}</b></span></div>
          </div>
          <div className="channelChecks">
            {sites.map(site => {
              const locked = batchRunning || isRunning(site) || submittingSiteIds.includes(site.id);
              const displayState = siteDisplayState(site);
              return <label key={site.id} className={`${visibleSiteIds.includes(site.id) ? "checked" : ""} ${!site.enabled ? "disabled" : ""}`}>
                <input type="checkbox" aria-label={`顯示 SITE ${site.id}`} checked={visibleSiteIds.includes(site.id)} disabled={locked} onChange={() => toggleSite(site.id)}/>
                <span>SITE {site.id}</span><small>{displayState.label}</small>
              </label>;
            })}
          </div>
        </section>

        <section className="operationConfig" aria-label="工作參數">
          <div className="compactFile">
            <div><b>{imageAsset?.name ?? "選擇 Programming Image Asset BIN 檔案"}</b><small>{imageAsset ? `${(imageAsset.size / 1024).toFixed(1)} KB · BIN` : "Program / Verify 共用 · Max 16 MiB"}</small></div>
            <label>瀏覽檔案<input aria-label="選擇 Programming Image Asset 檔案" type="file" accept=".bin,application/octet-stream" disabled={batchRunning} onChange={event => setImageAsset(event.target.files?.[0] ?? null)}/></label>
          </div>
          <div className="compactRead">
            <label>READ Offset<input aria-label="READ logical flash offset" type="number" min="0" step="1" value={readOffset} disabled={batchRunning} onChange={event => setReadOffset(event.target.value)}/></label>
            <label>READ Length<input aria-label="READ byte length" type="number" min="1" step="1" value={readLength} disabled={batchRunning} onChange={event => setReadLength(event.target.value)}/></label>
          </div>
        </section>

        <section className="batchPanel" aria-labelledby="batch-title">
          <div className="batchInfo">
            <div><p className="eyebrow">BATCH CONTROL</p><h2 id="batch-title">批次控制</h2><small>目標：{batchTargetText}</small></div>
            <div className="statusSummary" aria-label="選取 Site 狀態摘要">
              <span>待命 <b>{statusCounts.idle}</b></span><span className="busy">工作中 <b>{statusCounts.busy}</b></span><span className="success">成功 <b>{statusCounts.success}</b></span><span className="failed">取消 <b>{statusCounts.cancelled}</b></span><span className="failed">失敗 <b>{statusCounts.failed}</b></span>
            </div>
          </div>
          <div className="batchActions">
            <div className="batchOperationChoices" role="group" aria-label="選取批次操作">
              {operationOrder.map(operation => {
                const selected = selectedBatchOperations.includes(operation);
                return <label key={operation} className={selected ? "selected" : ""}>
                  <input type="checkbox" aria-label={`批次操作：${operationLabels[operation]}`} checked={selected} onChange={() => toggleBatchOperation(operation)} disabled={batchRunning}/>
                  <span>{operationSymbols[operation]}</span><b>{operationLabels[operation]}</b>
                </label>;
              })}
            </div>
            <div className="batchExecutionControls">
              <button type="button" className="executeBatch" aria-label={selectedBatchOperations.length ? `批次執行：${selectedBatchOperations.map(operation => operationLabels[operation]).join("、")}` : "批次執行：尚未選擇操作"} onClick={() => void runBatch(selectedBatchOperations)} disabled={batchRunning || selectedBatchOperations.length === 0 || selectedBatchOperations.some(batchDisabled)}><span>▶</span>{batchRunning ? "批次執行中" : `批次執行（${selectedBatchOperations.length}）`}</button>
              <button type="button" className="cancelBatch" aria-label="取消批次工作" onClick={() => void cancelBatch()} disabled={!batchRunning || batchCancelling}><span>■</span>{batchCancelling ? "取消中…" : "取消批次"}</button>
            </div>
          </div>
          {visibleSites.some(site => !site.enabled) && <div className="warning">選取項目包含未啟用 Site；取消勾選後才能執行批次工作。</div>}
          {imageAsset && imageAsset.size > MAX_IMAGE_ASSET_BYTES && <div className="warning">Programming Image Asset 超過 16 MiB 限制。</div>}
        </section>

        <section className="overviewCard" aria-labelledby="overview-title">
          <div className="overviewHead"><div><p className="eyebrow">LIVE SITE STATUS</p><h2 id="overview-title">Site 執行狀態</h2></div><small>REST polling 500 ms</small></div>
          <div className="channelTableWrap">
            <table className="channelTable">
              <thead><tr><th>Site</th><th>目標／介面</th><th>目前工作</th><th>狀態</th><th>進度</th><th>獨立操作</th></tr></thead>
              <tbody>
                {visibleSites.map(site => {
                  const displayState = siteDisplayState(site);
                  return <tr key={site.id}>
                    <td><button className="channelDetails" onClick={() => setDetailsSiteId(site.id)}><b>SITE {site.id}</b><small>詳細資料 ↗</small></button></td>
                    <td><b>{site.target ?? "STM32F103C8T6"}</b><small>{site.interface ?? "Mock / SWD"}</small></td>
                    <td>{site.operation ? operationLabels[site.operation] : "—"}{site.error && <small className="errorText">{site.error}</small>}</td>
                    <td><span className={`state ${displayState.state}`}>{displayState.label}</span></td>
                    <td><div className="tableProgress"><div className="track"><i style={{ width: `${site.progress}%` }}/></div><b>{Math.round(site.progress)}%</b></div></td>
                    <td><div className="rowActions">
                      {(Object.keys(operationLabels) as Operation[]).map(operation => <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`SITE ${site.id} ${operationLabels[operation]}`} title={operationLabels[operation]} onClick={() => void runSite(site.id, operation)} disabled={operationDisabled(site, operation)}>{operationSymbols[operation]}</button>)}
                      <button className="stop" aria-label={`取消 SITE ${site.id} 工作`} title="取消工作" onClick={() => void cancel(site.id)} disabled={!isRunning(site)}>■</button>
                      {site.stage === "success" && site.jobId && site.outputFile && <a className="rowDownload" aria-label={`下載 SITE ${site.id} 讀取檔案`} title="下載 BIN" href={readDownloadUrl(apiBase, site.jobId, site.outputFile)}>↓</a>}
                    </div></td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="logCard">
          <div className="logHead"><div><span/>LIVE JOB LOG</div><button onClick={() => setLogs([])}>清除</button></div>
          <pre aria-label="Live job log">{logs.length ? logs.map(log => <span key={log.id} data-level={log.level} style={log.level === "error" ? { display: "block", color: "var(--red)", background: "color-mix(in srgb, var(--red) 10%, transparent)", borderLeft: "3px solid var(--red)", paddingLeft: "8px", marginLeft: "-8px", fontWeight: 700 } : { display: "block" }}>{log.text}</span>) : "Log cleared."}</pre>
        </section>
      </section>

      {detailsSite && <div className="modalBackdrop" onClick={() => setDetailsSiteId(null)}><section className="details" onClick={event => event.stopPropagation()}>
        <div className="detailsHead"><div><p className="eyebrow">JOB INSPECTOR</p><h2>Site {detailsSite.id} 詳細資料</h2></div><button aria-label="關閉詳細資料" onClick={() => setDetailsSiteId(null)}>×</button></div>
        <dl><div><dt>Plasma Web REST Gateway</dt><dd>{apiBase}</dd></div><div><dt>Facility</dt><dd>{ppu?.facility_id ?? "—"}</dd></div><div><dt>PPU</dt><dd>{ppu?.ppu_id ?? "—"}</dd></div><div><dt>Job ID</dt><dd>{detailsSite.jobId ?? "—"}</dd></div><div><dt>Operation</dt><dd>{detailsSite.operation?.toUpperCase() ?? "—"}</dd></div><div><dt>Job State</dt><dd>{detailsSite.stage.toUpperCase()}</dd></div><div><dt>Batch State</dt><dd>{detailsBatchState ? batchStateLabels[detailsBatchState] : "—"}</dd></div><div><dt>Programming Image Asset</dt><dd>{detailsSite.file ?? "—"}</dd></div><div><dt>Progress</dt><dd>{detailsSite.progress.toFixed(1)}%</dd></div><div><dt>Protocol</dt><dd>REST → Plasma v3.3 TCP</dd></div><div><dt>Target</dt><dd>{detailsSite.target ?? "STM32F103C8T6"} ({detailsSite.interface ?? "Mock"})</dd></div></dl>
        <p>Job State 保留 Python Job Manager 回傳的真實結果；Batch State 描述該 Site 在本次批次流程的結果。Mock 測試不代表 Z2、FPGA I/O 或實體 IC 已完成驗證。</p>
      </section></div>}
    </main>
  );
}