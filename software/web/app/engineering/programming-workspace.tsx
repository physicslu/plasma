"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { BatchLifecycle } from "../batch-lifecycle";
import { useI18n } from "../i18n";
import {
  beginEngineeringSession,
  cancelJob,
  DEFAULT_API_BASE,
  engineeringTargetApiBase,
  getEngineeringTargets,
  getJob,
  getPPUStatus,
  normalizeApiBase,
  PlasmaSubmissionBlockedError,
  readDownloadUrl,
  startJob,
} from "../plasma-api";
import type {
  EngineeringTargetCatalog,
  JobSnapshot,
  JobState,
  Operation,
  PPUSnapshot,
  SiteSnapshot,
} from "../plasma-api";

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
  operation?: Operation;
  jobId?: string;
  target?: string;
  interface?: string;
  error?: string;
  outputFile?: string;
};

type TargetSelection = { facilityId: string; ppuId: string };
type ConnectionState = "connecting" | "online" | "offline";
type BatchSiteState = "running" | "cancelling" | "success" | "cancelled" | "failed";
type LogEntry = { id: number; text: string; error: boolean };

const MAX_FIRMWARE_BYTES = 16 * 1024 * 1024;
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
  return {
    id: snapshot.site_id,
    enabled: snapshot.enabled,
    stage: existing?.stage ?? "idle",
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
  if (facility.ppus.some(item => item.ppu_id === selection.ppuId)) return selection;
  return { facilityId: facility.facility_id, ppuId: facility.ppus[0]?.ppu_id ?? "" };
}

export default function ProgrammingWorkspace() {
  const { t } = useI18n();
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_BASE);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [connectionGeneration, setConnectionGeneration] = useState(0);
  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selection, setSelection] = useState<TargetSelection>({ facilityId: "", ppuId: "" });
  const [ppu, setPPU] = useState<PPUSnapshot | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteIds, setSelectedSiteIds] = useState<number[]>([]);
  const [selectedOperations, setSelectedOperations] = useState<Operation[]>([]);
  const [firmware, setFirmware] = useState<File | null>(null);
  const [readOffset, setReadOffset] = useState("0");
  const [readLength, setReadLength] = useState("256");
  const [submittingSiteIds, setSubmittingSiteIds] = useState<number[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchCancelling, setBatchCancelling] = useState(false);
  const [batchSiteStates, setBatchSiteStates] = useState<Record<number, BatchSiteState>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const trackedJobs = useRef<Record<number, string>>({});
  const submissionGenerations = useRef<Record<number, number>>({});
  const batchLifecycle = useRef<BatchLifecycle | null>(null);
  const cancelRequests = useRef<Set<string>>(new Set());
  const engineeringSessionId = useRef<string | null>(null);
  const logSequence = useRef(0);

  const facility = catalog?.facilities.find(item => item.facility_id === selection.facilityId) ?? null;
  const selectedPPU = facility?.ppus.find(item => item.ppu_id === selection.ppuId) ?? null;
  const targetApiBase = selection.facilityId && selection.ppuId
    ? engineeringTargetApiBase(apiBase, selection.facilityId, selection.ppuId)
    : null;
  const selectedSites = sites.filter(site => selectedSiteIds.includes(site.id));
  const readRangeValid = Number.isInteger(Number(readOffset))
    && Number(readOffset) >= 0
    && Number.isInteger(Number(readLength))
    && Number(readLength) > 0;
  const targetLocked = batchRunning || submittingSiteIds.length > 0 || sites.some(isRunning);

  const appendLog = useCallback((message: string, error = false) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs(current => [
      ...current.slice(-79),
      { id: ++logSequence.current, text: `${time}  ${message}`, error },
    ]);
  }, []);

  const resetTargetRuntime = useCallback(() => {
    trackedJobs.current = {};
    submissionGenerations.current = {};
    cancelRequests.current.clear();
    batchLifecycle.current = null;
    setPPU(null);
    setSites([]);
    setSelectedSiteIds([]);
    setBatchSiteStates({});
    setSubmittingSiteIds([]);
    setBatchRunning(false);
    setBatchCancelling(false);
  }, []);

  const switchTarget = useCallback((next: TargetSelection) => {
    resetTargetRuntime();
    setSelection(next);
    if (next.facilityId && next.ppuId) appendLog(`[TARGET] ${next.facilityId} / ${next.ppuId}`);
  }, [appendLog, resetTargetRuntime]);

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
    const restore = window.requestAnimationFrame(() => {
      const savedApi = window.localStorage.getItem("plasma-api-base");
      if (!savedApi) return;
      try {
        const normalized = normalizeApiBase(savedApi);
        setApiBase(normalized);
        setApiDraft(normalized);
      } catch {
        window.localStorage.removeItem("plasma-api-base");
      }
    });
    return () => window.cancelAnimationFrame(restore);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const session = await beginEngineeringSession(
          apiBase,
          engineeringSessionId.current ?? undefined,
        );
        engineeringSessionId.current = session.session_id;
        if (cancelled) return;
        const next = await getEngineeringTargets(apiBase);
        if (cancelled) return;
        setCatalog(next);
        setCatalogError(null);
        setConnection("online");
        setSelection(current => validSelection(next, current));
        appendLog(`[ENGINEERING] Provider ${next.provider.toUpperCase()} · ${next.facility_count} Facilities · ${next.ppu_count} PPUs · ${next.site_count} Sites`);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "Engineering target provider unavailable";
        resetTargetRuntime();
        setCatalog(null);
        setCatalogError(message);
        setSelection({ facilityId: "", ppuId: "" });
        setConnection("offline");
        appendLog(`[ENGINEERING] Provider unavailable · ${message}`, true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, connectionGeneration, appendLog, resetTargetRuntime]);

  useEffect(() => {
    if (!targetApiBase) return;
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
        setSelectedSiteIds(current => {
          const retained = current.filter(id => availableIds.has(id));
          if (retained.length) return retained;
          return status.sites.filter(site => site.enabled).map(site => site.site_id);
        });

        const jobIds = [...new Set(Object.values(trackedJobs.current))];
        const jobs = await Promise.all(jobIds.map(jobId => getJob(targetApiBase!, jobId)));
        if (stopped) return;
        jobs.forEach(job => {
          if (trackedJobs.current[job.site_id] !== job.job_id) return;
          applyJob(job);
          if (terminalStates.has(job.state)) delete trackedJobs.current[job.site_id];
        });
      } catch (error) {
        if (!stopped) appendLog(`[TARGET] Status failed · ${error instanceof Error ? error.message : "unknown error"}`, true);
      } finally {
        if (!stopped) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [targetApiBase, connectionGeneration, applyJob, appendLog]);

  function connect(event: FormEvent) {
    event.preventDefault();
    if (targetLocked) {
      appendLog("[NET] Gateway change blocked while a target Job is active", true);
      return;
    }
    try {
      const normalized = normalizeApiBase(apiDraft);
      window.localStorage.setItem("plasma-api-base", normalized);
      resetTargetRuntime();
      setCatalog(null);
      setCatalogError(null);
      setConnection("connecting");
      setApiDraft(normalized);
      setApiBase(normalized);
      setConnectionGeneration(current => current + 1);
    } catch (error) {
      appendLog(`[NET] ${error instanceof Error ? error.message : "Invalid Gateway URL"}`, true);
    }
  }

  function selectFacility(facilityId: string) {
    if (targetLocked) return;
    const nextFacility = catalog?.facilities.find(item => item.facility_id === facilityId);
    switchTarget({
      facilityId,
      ppuId: nextFacility?.ppus[0]?.ppu_id ?? "",
    });
  }

  function selectPPU(ppuId: string) {
    if (targetLocked) return;
    switchTarget({ facilityId: selection.facilityId, ppuId });
  }

  function toggleSite(siteId: number) {
    if (batchRunning) return;
    setSelectedSiteIds(current => current.includes(siteId)
      ? current.filter(id => id !== siteId)
      : [...current, siteId].sort((left, right) => left - right));
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : operationOrder.filter(item => current.includes(item) || item === operation));
  }

  function operationDisabled(site: Site, operation: Operation, forBatch = false): boolean {
    if (!targetApiBase || connection !== "online" || !site.enabled || isRunning(site)) return true;
    if (!forBatch && batchRunning) return true;
    if (submittingSiteIds.includes(site.id)) return true;
    if ((operation === "program" || operation === "verify") && !firmware) return true;
    if ((operation === "program" || operation === "verify") && Boolean(firmware && firmware.size > MAX_FIRMWARE_BYTES)) return true;
    if (operation === "read" && !readRangeValid) return true;
    return false;
  }

  function batchDisabled(operation: Operation): boolean {
    return selectedSites.length === 0 || selectedSites.some(site => operationDisabled(site, operation, true));
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
      const job = await startJob(targetApiBase, {
        siteId,
        operation,
        firmware: operation === "erase" || operation === "read" ? null : firmware,
        engineeringSessionId: engineeringSessionId.current ?? undefined,
        offset: operation === "read" ? Number(readOffset) : undefined,
        length: operation === "read" ? Number(readLength) : undefined,
        submissionGuard,
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
      appendLog(`[SITE ${siteId}] ${operation.toUpperCase()} accepted · ${job.job_id}`);
      return job;
    } catch (error) {
      if (error instanceof PlasmaSubmissionBlockedError) return;
      const message = error instanceof Error ? error.message : "unknown error";
      appendLog(`[SITE ${siteId}] Submit failed · ${message}`, true);
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
      appendLog(`[SITE ${siteId}] Cancel requested · ${jobId}`);
    } catch (error) {
      cancelRequests.current.delete(jobId);
      appendLog(`[SITE ${siteId}] Cancel failed · ${error instanceof Error ? error.message : "unknown error"}`, true);
    }
  }

  async function runBatch() {
    if (batchRunning || selectedOperations.length === 0 || selectedOperations.some(batchDisabled)) return;
    const siteIds = [...selectedSiteIds];
    const operations = [...selectedOperations];
    const lifecycle = new BatchLifecycle(siteIds);
    batchLifecycle.current = lifecycle;
    setBatchRunning(true);
    setBatchCancelling(false);
    setBatchSiteStates(Object.fromEntries(siteIds.map(id => [id, "running"])) as Record<number, BatchSiteState>);
    appendLog(`[BATCH] START ${operations.map(item => item.toUpperCase()).join(" → ")} · ${siteIds.map(id => `SITE ${id}`).join(", ")}`);
    try {
      await Promise.all(siteIds.map(async siteId => {
        for (const operation of operations) {
          if (!lifecycle.prepare(siteId, operation)) {
            setBatchSiteState(siteId, "cancelled");
            lifecycle.finish(siteId);
            return;
          }
          await new Promise(resolve => window.setTimeout(resolve, 0));
          if (!lifecycle.beginSubmit(siteId)) {
            setBatchSiteState(siteId, "cancelled");
            lifecycle.finish(siteId);
            return;
          }
          const job = await runSite(siteId, operation, true, () => lifecycle.canDispatch(siteId));
          if (!job) {
            setBatchSiteState(siteId, lifecycle.isCancelRequested(siteId) ? "cancelled" : "failed");
            lifecycle.finish(siteId);
            return;
          }
          if (lifecycle.accepted(siteId, job.job_id)) await requestCancel(siteId, job.job_id);
          try {
            const finalJob = await waitTerminal(job);
            if (lifecycle.isCancelRequested(siteId) || cancelRequests.current.has(job.job_id)) {
              setBatchSiteState(siteId, "cancelled");
              lifecycle.finish(siteId);
              return;
            }
            if (finalJob.state !== "success") {
              setBatchSiteState(siteId, finalJob.state === "cancelled" ? "cancelled" : "failed");
              lifecycle.finish(siteId);
              return;
            }
          } catch (error) {
            setBatchSiteState(siteId, lifecycle.isCancelRequested(siteId) ? "cancelled" : "failed");
            appendLog(`[SITE ${siteId}] Batch polling failed · ${error instanceof Error ? error.message : "unknown error"}`, true);
            lifecycle.finish(siteId);
            return;
          }
        }
        setBatchSiteState(siteId, "success");
        lifecycle.finish(siteId);
      }));
      appendLog(`[BATCH] ${lifecycle.cancelRequested ? "CANCELLED" : "COMPLETE"}`);
    } finally {
      if (batchLifecycle.current === lifecycle) batchLifecycle.current = null;
      setBatchRunning(false);
      setBatchCancelling(false);
    }
  }

  async function cancelBatch() {
    const lifecycle = batchLifecycle.current;
    if (!batchRunning || batchCancelling || !lifecycle) return;
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
    const lifecycle = batchLifecycle.current;
    if (batchRunning && lifecycle) {
      const jobId = lifecycle.cancelSite(siteId);
      setBatchSiteState(siteId, "cancelling");
      if (jobId) await requestCancel(siteId, jobId);
      return;
    }
    await requestCancel(siteId, site.jobId);
  }

  const statusCounts = selectedSites.reduce((counts, site) => {
    const batch = batchSiteStates[site.id];
    if (batch === "running" || batch === "cancelling" || isRunning(site)) counts.running += 1;
    else if (batch === "success" || site.stage === "success") counts.success += 1;
    else if (batch === "cancelled" || site.stage === "cancelled") counts.cancelled += 1;
    else if (batch === "failed" || ["failed", "timeout", "aborted"].includes(site.stage)) counts.failed += 1;
    else counts.idle += 1;
    return counts;
  }, { idle: 0, running: 0, success: 0, cancelled: 0, failed: 0 });

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
              <span>SITE {site.id}</span>
              <small>{site.enabled ? site.stage.toUpperCase() : "DISABLED"}</small>
            </label>
          ))}
        </div>
      </section>

      <section className="operationConfig" aria-label="Engineering programming parameters">
        <div className="compactFile">
          <div><b>{firmware?.name ?? t("engineeringProgramming.firmware")}</b><small>{firmware ? `${(firmware.size / 1024).toFixed(1)} KB` : t("engineeringProgramming.firmwareHint")}</small></div>
          <label>{t("engineeringProgramming.browse")}<input aria-label="Engineering Firmware file" type="file" accept=".bin,application/octet-stream" disabled={targetLocked} onChange={event => setFirmware(event.target.files?.[0] ?? null)} /></label>
        </div>
        <div className="compactRead">
          <label>READ Offset<input aria-label="Engineering READ offset" type="number" min="0" step="1" value={readOffset} disabled={batchRunning} onChange={event => setReadOffset(event.target.value)} /></label>
          <label>READ Length<input aria-label="Engineering READ length" type="number" min="1" step="1" value={readLength} disabled={batchRunning} onChange={event => setReadLength(event.target.value)} /></label>
        </div>
      </section>

      <section className="batchPanel engineeringBatchPanel" aria-label="Engineering batch control">
        <div className="batchInfo">
          <div><p className="eyebrow">E / P / V / R</p><h2>{t("engineeringProgramming.batchOperations")}</h2><small>{selectedSiteIds.map(id => `SITE ${id}`).join(", ") || t("engineeringProgramming.noSites")}</small></div>
          <div className="statusSummary">
            <span>{t("engineeringProgramming.idle")} <b>{statusCounts.idle}</b></span><span className="busy">{t("engineeringProgramming.running")} <b>{statusCounts.running}</b></span><span className="success">{t("engineeringProgramming.success")} <b>{statusCounts.success}</b></span><span className="failed">{t("engineeringProgramming.cancelled")} <b>{statusCounts.cancelled}</b></span><span className="failed">{t("engineeringProgramming.failed")} <b>{statusCounts.failed}</b></span>
          </div>
        </div>
        <div className="batchActions">
          <div className="batchOperationChoices" role="group" aria-label="Engineering batch operations">
            {operationOrder.map(operation => {
              const selected = selectedOperations.includes(operation);
              return <label key={operation} className={selected ? "selected" : ""}>
                <input type="checkbox" aria-label={`Engineering batch ${operation}`} checked={selected} disabled={batchRunning} onChange={() => toggleOperation(operation)} />
                <span>{operationCodes[operation]}</span><b>{t(`operation.${operation}`)}</b>
              </label>;
            })}
          </div>
          <div className="batchExecutionControls">
            <button type="button" className="executeBatch" onClick={() => void runBatch()} disabled={batchRunning || selectedOperations.length === 0 || selectedOperations.some(batchDisabled)}>▶ {t("engineeringProgramming.execute")}</button>
            <button type="button" className="cancelBatch" onClick={() => void cancelBatch()} disabled={!batchRunning || batchCancelling}>■ {batchCancelling ? t("engineeringProgramming.cancelling") : t("engineeringProgramming.cancel")}</button>
          </div>
        </div>
      </section>

      {firmware && firmware.size > MAX_FIRMWARE_BYTES && <div className="warning">{t("engineeringProgramming.firmwareTooLarge")}</div>}

      <section className="overviewCard" aria-label="Engineering Site status">
        <div className="overviewHead"><div><p className="eyebrow">LIVE PPU STATUS</p><h2>{ppu?.display_name ?? selectedPPU?.display_name ?? t("engineeringProgramming.selectedPpu")}</h2></div><small>REST polling 500 ms</small></div>
        <div className="channelTableWrap">
          <table className="channelTable">
            <thead><tr><th>Site</th><th>{t("engineeringProgramming.targetInterface")}</th><th>{t("engineeringProgramming.operation")}</th><th>{t("engineeringProgramming.state")}</th><th>{t("engineeringProgramming.progress")}</th><th>{t("engineeringProgramming.independent")}</th></tr></thead>
            <tbody>
              {selectedSites.map(site => (
                <tr key={site.id}>
                  <td><b>SITE {site.id}</b></td>
                  <td><b>{site.target ?? "—"}</b><small>{site.interface ?? "—"}</small></td>
                  <td>{site.operation?.toUpperCase() ?? "—"}{site.error && <small className="errorText">{site.error}</small>}</td>
                  <td><span className={`state ${site.stage}`}>{site.stage.toUpperCase()}</span></td>
                  <td><div className="tableProgress"><div className="track"><i style={{ width: `${site.progress}%` }} /></div><b>{Math.round(site.progress)}%</b></div></td>
                  <td><div className="rowActions">
                    {operationOrder.map(operation => <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`SITE ${site.id} ${t(`operation.${operation}`)}`} title={t(`operation.${operation}`)} disabled={operationDisabled(site, operation)} onClick={() => void runSite(site.id, operation)}>{operationCodes[operation]}</button>)}
                    <button className="stop" aria-label={`Cancel SITE ${site.id}`} disabled={!isRunning(site)} onClick={() => void cancelSite(site.id)}>■</button>
                    {site.stage === "success" && site.jobId && site.outputFile && targetApiBase && <a className="rowDownload" aria-label={`Download SITE ${site.id} read file`} href={readDownloadUrl(targetApiBase, site.jobId, site.outputFile)}>↓</a>}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="logCard engineeringLogCard">
        <div className="logHead"><div><span />{t("engineeringProgramming.jobLog")}</div><button type="button" onClick={() => setLogs([])}>{t("engineeringProgramming.clear")}</button></div>
        <pre aria-label="Engineering job log">{logs.length ? logs.map(log => <span key={log.id} data-level={log.error ? "error" : "info"}>{log.text}</span>) : "Log cleared."}</pre>
      </section>
    </section>
  );
}
