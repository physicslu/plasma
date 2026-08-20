"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import {
  beginEngineeringSession,
  cancelJob,
  DEFAULT_API_BASE,
  engineeringTargetApiBase,
  getEngineeringTargets,
  getJob,
  getPPUStatus,
  startJob,
} from "../plasma-api";
import type {
  EngineeringFacilityTarget,
  EngineeringPPUTarget,
  EngineeringTargetCatalog,
  JobSnapshot,
  Operation,
  SiteSnapshot,
} from "../plasma-api";
import "./fleet.css";
import "./production-prototype.css";

type SiteRunState = "ready" | "running" | "success" | "failed" | "cancelled";
type BatchState = "idle" | "running" | "cancelling" | "complete" | "partial" | "cancelled";

type SiteRuntime = {
  id: number;
  enabled: boolean;
  selected: boolean;
  state: SiteRunState;
  progress: number;
  operation?: Operation;
  jobId?: string;
  error?: string;
  target?: string | null;
  interface?: string | null;
};

type PPURuntime = {
  target: EngineeringPPUTarget;
  sites: SiteRuntime[];
  loading: boolean;
  error?: string;
};

type ActiveJob = {
  ppuId: string;
  targetApiBase: string;
  siteId: number;
  jobId: string;
};

type LogEntry = {
  id: number;
  time: string;
  level: "INFO" | "WARN" | "ERROR";
  text: string;
};

const MAX_IMAGE_BYTES = 16 * 1024 * 1024;
const POLL_INTERVAL_MS = 300;
const POLL_LIMIT = 600;
const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };
const terminalStates = new Set(["success", "failed", "cancelled", "timeout", "aborted"]);

const copy = {
  "zh-TW": {
    eyebrow: "PRODUCTION MODE · MOCK PROTOTYPE",
    title: "Factory Production Console",
    subtitle: "Facility → PPU Production Set → 跨 PPU / 跨 Site 並行批次",
    boundary: "此頁使用 Python Mock PPU Provider 驗證多 PPU 執行。Plasma Manager 仍維持唯讀；本 Prototype 不授權任何 real PPU 遠端寫入。",
    provider: "Mock PPU Provider",
    loading: "正在連接 Mock Provider…",
    offline: "Mock Provider 無法使用。請確認 Plasma Web REST Gateway 已啟用 Engineering Mock Provider。",
    facility: "Facility",
    ppuSelection: "PPU 選擇",
    set: "SET",
    setHint: "SET 後，下方只顯示這次量產要操作的 PPU。",
    noPpu: "請至少選擇一台 PPU。",
    productionSet: "Production Set",
    noSet: "尚未建立 Production Set。",
    selectedPpus: "PPUs",
    selectedSites: "Sites",
    operations: "批次操作",
    image: "Programming Image (.bin)",
    imageHint: "Program / Verify 需要 Image Asset，最大 16 MiB。",
    execute: "EXECUTE BATCH",
    cancelAll: "CANCEL BATCH",
    cancelPpu: "Cancel PPU",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    failed: "FAIL",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    complete: "COMPLETE",
    batch: "Batch",
    ppuState: "PPU State",
    selectAllSites: "Select all Sites",
    clearSites: "Clear Sites",
    log: "Production Prototype Log",
    clearLog: "清除 Log",
    imageTooLarge: "Programming Image 超過 16 MiB。",
    imageRequired: "Program / Verify 需要先選擇 Programming Image。",
    chooseOperation: "請至少選擇一個操作。",
    noSelectedSites: "Production Set 內沒有選取 Site。",
  },
  "en-US": {
    eyebrow: "PRODUCTION MODE · MOCK PROTOTYPE",
    title: "Factory Production Console",
    subtitle: "Facility → PPU Production Set → concurrent execution across PPUs and Sites",
    boundary: "This page uses the Python Mock PPU Provider to validate multi-PPU execution. Plasma Manager remains read-only; this prototype grants no remote write authority to real PPUs.",
    provider: "Mock PPU Provider",
    loading: "Connecting to Mock Provider…",
    offline: "Mock Provider is unavailable. Enable the Engineering Mock Provider on the Plasma Web REST Gateway.",
    facility: "Facility",
    ppuSelection: "PPU Selection",
    set: "SET",
    setHint: "After SET, only PPUs in this Production Set are shown below.",
    noPpu: "Select at least one PPU.",
    productionSet: "Production Set",
    noSet: "No Production Set has been created.",
    selectedPpus: "PPUs",
    selectedSites: "Sites",
    operations: "Batch Operations",
    image: "Programming Image (.bin)",
    imageHint: "Program / Verify requires an Image Asset, max 16 MiB.",
    execute: "EXECUTE BATCH",
    cancelAll: "CANCEL BATCH",
    cancelPpu: "Cancel PPU",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    failed: "FAIL",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    complete: "COMPLETE",
    batch: "Batch",
    ppuState: "PPU State",
    selectAllSites: "Select all Sites",
    clearSites: "Clear Sites",
    log: "Production Prototype Log",
    clearLog: "Clear Log",
    imageTooLarge: "Programming Image exceeds 16 MiB.",
    imageRequired: "Program / Verify requires a Programming Image.",
    chooseOperation: "Select at least one operation.",
    noSelectedSites: "No Site is selected in the Production Set.",
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

function runtimeFromStatus(snapshot: SiteSnapshot): SiteRuntime {
  return {
    id: snapshot.site_id,
    enabled: snapshot.enabled,
    selected: snapshot.enabled,
    state: "ready",
    progress: 0,
    target: snapshot.target,
    interface: snapshot.interface,
  };
}

function orderedOperations(selected: Operation[]): Operation[] {
  return operationOrder.filter(operation => selected.includes(operation));
}

function ppuStatus(runtime: PPURuntime): SiteRunState | "partial" {
  const sites = runtime.sites.filter(site => site.selected);
  if (sites.length === 0) return "ready";
  if (sites.some(site => site.state === "running")) return "running";
  if (sites.every(site => site.state === "success")) return "success";
  if (sites.every(site => site.state === "cancelled")) return "cancelled";
  if (sites.some(site => site.state === "failed")) return "failed";
  if (sites.some(site => site.state === "success" || site.state === "cancelled")) return "partial";
  return "ready";
}

export default function FleetPage() {
  const { locale, t } = useI18n();
  const text = copy[locale];
  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [facilityId, setFacilityId] = useState("");
  const [draftPpuIds, setDraftPpuIds] = useState<string[]>([]);
  const [activeFacilityId, setActiveFacilityId] = useState("");
  const [activePpuIds, setActivePpuIds] = useState<string[]>([]);
  const [runtimes, setRuntimes] = useState<Record<string, PPURuntime>>({});
  const [selectedOperations, setSelectedOperations] = useState<Operation[]>([]);
  const [imageAsset, setImageAsset] = useState<File | null>(null);
  const [batchState, setBatchState] = useState<BatchState>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const currentJobs = useRef<Map<string, ActiveJob>>(new Map());
  const cancelAllRequested = useRef(false);
  const cancelledPpus = useRef<Set<string>>(new Set());
  const logSequence = useRef(0);

  const appendLog = useCallback((textValue: string, level: LogEntry["level"] = "INFO") => {
    const entry: LogEntry = { id: ++logSequence.current, time: nowTime(), level, text: textValue };
    setLogs(current => [...current, entry].slice(-500));
  }, []);

  useEffect(() => {
    let stopped = false;
    void (async () => {
      try {
        const session = await beginEngineeringSession(DEFAULT_API_BASE);
        const next = await getEngineeringTargets(DEFAULT_API_BASE);
        if (stopped) return;
        setSessionId(session.session_id);
        setCatalog(next);
        setProviderError(null);
        const firstFacility = next.facilities[0]?.facility_id ?? "";
        setFacilityId(firstFacility);
        setDraftPpuIds([]);
        appendLog(`[PROVIDER] ${next.provider.toUpperCase()} · ${next.facility_count} Facilities · ${next.ppu_count} PPUs · ${next.site_count} Sites`);
      } catch (error) {
        if (stopped) return;
        const detail = error instanceof Error ? error.message : text.offline;
        setProviderError(detail);
        setCatalog(null);
        appendLog(`[PROVIDER] unavailable · ${detail}`, "ERROR");
      }
    })();
    return () => { stopped = true; };
  }, [appendLog, text.offline]);

  const facility: EngineeringFacilityTarget | null = useMemo(
    () => catalog?.facilities.find(item => item.facility_id === facilityId) ?? null,
    [catalog, facilityId],
  );

  const activeFacility: EngineeringFacilityTarget | null = useMemo(
    () => catalog?.facilities.find(item => item.facility_id === activeFacilityId) ?? null,
    [catalog, activeFacilityId],
  );

  const activeTargets = useMemo(
    () => activeFacility?.ppus.filter(ppu => activePpuIds.includes(ppu.ppu_id)) ?? [],
    [activeFacility, activePpuIds],
  );

  const batchRunning = batchState === "running" || batchState === "cancelling";

  const summary = useMemo(() => {
    const sites = Object.values(runtimes).flatMap(runtime => runtime.sites.filter(site => site.selected));
    return {
      ppus: activeTargets.length,
      sites: sites.length,
      running: sites.filter(site => site.state === "running").length,
      success: sites.filter(site => site.state === "success").length,
      failed: sites.filter(site => site.state === "failed").length,
      cancelled: sites.filter(site => site.state === "cancelled").length,
    };
  }, [runtimes, activeTargets.length]);

  const updateSite = useCallback((ppuId: string, siteId: number, patch: Partial<SiteRuntime>) => {
    setRuntimes(current => {
      const runtime = current[ppuId];
      if (!runtime) return current;
      return {
        ...current,
        [ppuId]: {
          ...runtime,
          sites: runtime.sites.map(site => site.id === siteId ? { ...site, ...patch } : site),
        },
      };
    });
  }, []);

  function toggleDraftPpu(ppuId: string) {
    if (batchRunning) return;
    setDraftPpuIds(current => current.includes(ppuId)
      ? current.filter(item => item !== ppuId)
      : [...current, ppuId]);
  }

  async function applyProductionSet() {
    if (!facility || draftPpuIds.length === 0 || batchRunning) return;
    const targets = facility.ppus.filter(ppu => draftPpuIds.includes(ppu.ppu_id));
    setActiveFacilityId(facility.facility_id);
    setActivePpuIds(targets.map(ppu => ppu.ppu_id));
    setBatchState("idle");
    cancelAllRequested.current = false;
    cancelledPpus.current.clear();
    currentJobs.current.clear();
    setRuntimes(Object.fromEntries(targets.map(target => [target.ppu_id, { target, sites: [], loading: true }])));
    appendLog(`[SET] ${facility.facility_id} · ${targets.map(target => target.ppu_id).join(", ")}`);

    const results = await Promise.allSettled(targets.map(async target => {
      const targetBase = engineeringTargetApiBase(DEFAULT_API_BASE, facility.facility_id, target.ppu_id);
      const status = await getPPUStatus(targetBase);
      return { target, status };
    }));

    setRuntimes(current => {
      const next = { ...current };
      results.forEach((result, index) => {
        const target = targets[index];
        if (result.status === "fulfilled") {
          next[target.ppu_id] = {
            target,
            loading: false,
            sites: result.value.status.sites.map(runtimeFromStatus),
          };
        } else {
          next[target.ppu_id] = {
            target,
            loading: false,
            sites: [],
            error: result.reason instanceof Error ? result.reason.message : "PPU status unavailable",
          };
        }
      });
      return next;
    });
  }

  function toggleSite(ppuId: string, siteId: number) {
    if (batchRunning) return;
    setRuntimes(current => {
      const runtime = current[ppuId];
      if (!runtime) return current;
      return {
        ...current,
        [ppuId]: {
          ...runtime,
          sites: runtime.sites.map(site => site.id === siteId && site.enabled
            ? { ...site, selected: !site.selected }
            : site),
        },
      };
    });
  }

  function selectSites(ppuId: string, selected: boolean) {
    if (batchRunning) return;
    setRuntimes(current => {
      const runtime = current[ppuId];
      if (!runtime) return current;
      return {
        ...current,
        [ppuId]: {
          ...runtime,
          sites: runtime.sites.map(site => ({ ...site, selected: site.enabled ? selected : false })),
        },
      };
    });
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : [...current, operation]);
  }

  async function waitForTerminal(
    ppuId: string,
    siteId: number,
    targetBase: string,
    jobId: string,
  ): Promise<SiteRunState> {
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      const job = await getJob(targetBase, jobId);
      const progress = Math.round(Number(job.progress_percent ?? 0));
      updateSite(ppuId, siteId, {
        state: terminalStates.has(job.state) ? undefined : "running",
        progress,
        operation: job.operation,
        jobId: job.job_id,
      });
      if (terminalStates.has(job.state)) {
        if (job.state === "success") return "success";
        if (job.state === "cancelled") return "cancelled";
        return "failed";
      }
      await delay(POLL_INTERVAL_MS);
    }
    throw new Error(`Job ${jobId} polling timed out`);
  }

  async function runSiteSequence(
    facilityValue: string,
    ppu: EngineeringPPUTarget,
    siteId: number,
    operations: Operation[],
  ): Promise<SiteRunState> {
    const targetBase = engineeringTargetApiBase(DEFAULT_API_BASE, facilityValue, ppu.ppu_id);
    try {
      updateSite(ppu.ppu_id, siteId, { state: "running", progress: 0, error: undefined });
      for (const operation of operations) {
        if (cancelAllRequested.current || cancelledPpus.current.has(ppu.ppu_id)) {
          updateSite(ppu.ppu_id, siteId, { state: "cancelled", progress: 0 });
          return "cancelled";
        }
        appendLog(`[JOB] START · ${ppu.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`);
        const job = await startJob(targetBase, {
          siteId,
          operation,
          assetFile: imageAsset,
          engineeringSessionId: sessionId ?? undefined,
          offset: 0,
          length: 256,
          submissionGuard: () => !cancelAllRequested.current && !cancelledPpus.current.has(ppu.ppu_id),
        });
        const jobKey = `${ppu.ppu_id}:${siteId}`;
        currentJobs.current.set(jobKey, {
          ppuId: ppu.ppu_id,
          targetApiBase: targetBase,
          siteId,
          jobId: job.job_id,
        });
        updateSite(ppu.ppu_id, siteId, {
          state: "running",
          progress: Math.round(Number(job.progress_percent ?? 0)),
          operation,
          jobId: job.job_id,
        });
        if (cancelAllRequested.current || cancelledPpus.current.has(ppu.ppu_id)) {
          await cancelJob(targetBase, job.job_id).catch(() => undefined);
        }
        const terminal = await waitForTerminal(ppu.ppu_id, siteId, targetBase, job.job_id);
        currentJobs.current.delete(jobKey);
        if (terminal !== "success") {
          updateSite(ppu.ppu_id, siteId, { state: terminal, progress: terminal === "failed" ? 0 : 100 });
          appendLog(`[JOB] ${terminal.toUpperCase()} · ${ppu.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`, terminal === "failed" ? "ERROR" : "WARN");
          return terminal;
        }
        appendLog(`[JOB] PASS · ${ppu.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`);
      }
      updateSite(ppu.ppu_id, siteId, { state: "success", progress: 100 });
      return "success";
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Job failed";
      updateSite(ppu.ppu_id, siteId, { state: "failed", progress: 0, error: detail });
      appendLog(`[JOB] FAIL · ${ppu.ppu_id} · ${siteLabel(siteId)} · ${detail}`, "ERROR");
      return "failed";
    }
  }

  async function executeBatch() {
    if (batchRunning || !activeFacilityId || activeTargets.length === 0) return;
    const operations = orderedOperations(selectedOperations);
    if (operations.length === 0) {
      appendLog(`[BAT] BLOCKED · ${text.chooseOperation}`, "WARN");
      return;
    }
    if (operations.some(operation => operation === "program" || operation === "verify") && !imageAsset) {
      appendLog(`[BAT] BLOCKED · ${text.imageRequired}`, "WARN");
      return;
    }
    const selected = activeTargets.flatMap(ppu => {
      const runtime = runtimes[ppu.ppu_id];
      return (runtime?.sites ?? []).filter(site => site.selected && site.enabled).map(site => ({ ppu, siteId: site.id }));
    });
    if (selected.length === 0) {
      appendLog(`[BAT] BLOCKED · ${text.noSelectedSites}`, "WARN");
      return;
    }

    cancelAllRequested.current = false;
    cancelledPpus.current.clear();
    currentJobs.current.clear();
    setBatchState("running");
    setRuntimes(current => Object.fromEntries(Object.entries(current).map(([ppuId, runtime]) => [ppuId, {
      ...runtime,
      sites: runtime.sites.map(site => site.selected
        ? { ...site, state: "ready" as const, progress: 0, jobId: undefined, error: undefined }
        : site),
    }])));
    appendLog(`[BAT] START · ${activeTargets.length} PPUs · ${selected.length} Sites · ${operations.map(operation => operation.toUpperCase()).join(" → ")}`);

    const results = await Promise.allSettled(
      selected.map(item => runSiteSequence(activeFacilityId, item.ppu, item.siteId, operations)),
    );
    const values = results.map(result => result.status === "fulfilled" ? result.value : "failed");
    if (values.every(value => value === "success")) {
      setBatchState("complete");
      appendLog(`[BAT] COMPLETE · ${selected.length}/${selected.length} Sites PASS`);
    } else if (values.every(value => value === "cancelled")) {
      setBatchState("cancelled");
      appendLog(`[BAT] CANCELLED · ${selected.length} Sites`, "WARN");
    } else {
      setBatchState("partial");
      const pass = values.filter(value => value === "success").length;
      const failed = values.filter(value => value === "failed").length;
      const cancelled = values.filter(value => value === "cancelled").length;
      const groups = [`success: ${pass}`];
      if (cancelled) groups.push(`cancelled: ${cancelled}`);
      if (failed) groups.push(`failed: ${failed}`);
      appendLog(`[BAT] PARTIAL · ${groups.join(" · ")}`, failed ? "ERROR" : "WARN");
    }
  }

  async function cancelActiveJobs(filterPpuId?: string) {
    const jobs = [...currentJobs.current.values()].filter(job => !filterPpuId || job.ppuId === filterPpuId);
    await Promise.allSettled(jobs.map(job => cancelJob(job.targetApiBase, job.jobId)));
  }

  async function cancelBatch() {
    if (!batchRunning) return;
    cancelAllRequested.current = true;
    setBatchState("cancelling");
    appendLog("[BAT] CANCEL REQUESTED", "WARN");
    await cancelActiveJobs();
  }

  async function cancelPPU(ppuId: string) {
    if (!batchRunning) return;
    cancelledPpus.current.add(ppuId);
    appendLog(`[PPU] CANCEL REQUESTED · ${ppuId}`, "WARN");
    await cancelActiveJobs(ppuId);
  }

  const batchLabel = batchState === "complete"
    ? text.complete
    : batchState === "partial"
      ? text.partial
      : batchState === "cancelled"
        ? text.cancelled
        : batchState === "running" || batchState === "cancelling"
          ? text.running
          : text.ready;

  return (
    <main className="productionPrototypePage">
      <section className="productionPrototypeShell">
        <header className="productionPrototypeHeading">
          <div>
            <p>{text.eyebrow}</p>
            <h1>{text.title}</h1>
            <span>{text.subtitle}</span>
          </div>
          <div className={`prototypeProvider ${providerError ? "offline" : catalog ? "online" : "loading"}`}>
            <i />
            <div><small>{text.provider}</small><b>{providerError ? "OFFLINE" : catalog ? "ONLINE" : "CONNECTING"}</b></div>
          </div>
        </header>

        <p className="prototypeBoundary">{text.boundary}</p>

        {!catalog && (
          <section className="prototypeNotice" role="status">
            <b>{providerError ? text.offline : text.loading}</b>
            {providerError && <span>{providerError}</span>}
          </section>
        )}

        {catalog && (
          <>
            <section className="prototypeTopologySummary" aria-label="Mock topology summary">
              <article><small>Facilities</small><b>{catalog.facility_count}</b></article>
              <article><small>PPUs</small><b>{catalog.ppu_count}</b></article>
              <article><small>Sites</small><b>{catalog.site_count}</b></article>
              <article><small>Provider</small><b>{catalog.provider.toUpperCase()}</b></article>
            </section>

            <section className="productionSelector" aria-label="Production Set selector">
              <div className="selectorFacility">
                <label htmlFor="production-facility">{text.facility}</label>
                <select
                  id="production-facility"
                  value={facilityId}
                  disabled={batchRunning}
                  onChange={event => {
                    setFacilityId(event.target.value);
                    setDraftPpuIds([]);
                  }}
                >
                  {catalog.facilities.map(item => <option value={item.facility_id} key={item.facility_id}>{item.display_name}</option>)}
                </select>
              </div>

              <div className="selectorPpus">
                <div className="selectorTitle"><b>{text.ppuSelection}</b><span>{facility?.ppus.length ?? 0} PPU</span></div>
                <div className="ppuChoiceGrid">
                  {(facility?.ppus ?? []).map(ppu => (
                    <label className={`ppuChoice ${draftPpuIds.includes(ppu.ppu_id) ? "selected" : ""}`} key={ppu.ppu_id}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${ppu.ppu_id}`}
                        checked={draftPpuIds.includes(ppu.ppu_id)}
                        disabled={batchRunning}
                        onChange={() => toggleDraftPpu(ppu.ppu_id)}
                      />
                      <span><b>{ppu.display_name}</b><small>{ppu.ppu_id}</small></span>
                      <em>{ppu.site_count} Sites</em>
                    </label>
                  ))}
                </div>
              </div>

              <div className="selectorSetAction">
                <button type="button" className="setButton" onClick={() => void applyProductionSet()} disabled={draftPpuIds.length === 0 || batchRunning}>{text.set}</button>
                <span>{draftPpuIds.length === 0 ? text.noPpu : text.setHint}</span>
              </div>
            </section>

            <section className="productionSet" aria-label={text.productionSet}>
              <header className="productionSetHead">
                <div><p>ACTIVE PRODUCTION SET</p><h2>{text.productionSet}</h2><span>{activeFacilityId || text.noSet}</span></div>
                <div className={`batchState batch-${batchState}`}><small>{text.batch}</small><b>{batchLabel}</b></div>
              </header>

              {activeTargets.length === 0 ? (
                <div className="emptyProductionSet">{text.noSet}</div>
              ) : (
                <>
                  <section className="productionSetSummary">
                    <article><small>{text.selectedPpus}</small><b>{summary.ppus}</b></article>
                    <article><small>{text.selectedSites}</small><b>{summary.sites}</b></article>
                    <article><small>RUNNING</small><b>{summary.running}</b></article>
                    <article><small>PASS</small><b>{summary.success}</b></article>
                    <article><small>FAIL</small><b>{summary.failed}</b></article>
                    <article><small>CANCELLED</small><b>{summary.cancelled}</b></article>
                  </section>

                  <section className="productionBatchToolbar">
                    <div className="batchOperations">
                      <span>{text.operations}</span>
                      {operationOrder.map(operation => (
                        <label key={operation}>
                          <input type="checkbox" checked={selectedOperations.includes(operation)} disabled={batchRunning} onChange={() => toggleOperation(operation)} />
                          <b>{operationCodes[operation]}</b> {t(`operation.${operation}`)}
                        </label>
                      ))}
                    </div>
                    <label className="productionImagePicker">
                      <span><b>{text.image}</b><small>{text.imageHint}</small></span>
                      <input
                        type="file"
                        accept=".bin,application/octet-stream"
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
                      <em>{imageAsset?.name ?? "—"}</em>
                    </label>
                    <div className="productionBatchActions">
                      <button type="button" className="executeBatchButton" onClick={() => void executeBatch()} disabled={batchRunning}>{text.execute}</button>
                      <button type="button" className="cancelBatchButton" onClick={() => void cancelBatch()} disabled={!batchRunning}>{text.cancelAll}</button>
                    </div>
                  </section>

                  <div className="productionPpuPrototypeStack">
                    {activeTargets.map(ppu => {
                      const runtime = runtimes[ppu.ppu_id];
                      const status = runtime ? ppuStatus(runtime) : "ready";
                      const statusText = status === "partial" ? text.partial : text[status];
                      return (
                        <article className={`productionPpuPrototype ppu-${status}`} data-production-ppu={ppu.ppu_id} key={ppu.ppu_id}>
                          <header>
                            <div className="productionPpuIdentity"><i /><div><small>{ppu.ppu_id}</small><h3>{ppu.display_name}</h3></div></div>
                            <div className="productionPpuStatus"><small>{text.ppuState}</small><b>{statusText}</b></div>
                            <div className="productionPpuControls">
                              <button type="button" onClick={() => selectSites(ppu.ppu_id, true)} disabled={batchRunning || !runtime}>{text.selectAllSites}</button>
                              <button type="button" onClick={() => selectSites(ppu.ppu_id, false)} disabled={batchRunning || !runtime}>{text.clearSites}</button>
                              <button type="button" className="cancelPpuButton" onClick={() => void cancelPPU(ppu.ppu_id)} disabled={!batchRunning}>{text.cancelPpu}</button>
                            </div>
                          </header>

                          {runtime?.loading && <div className="ppuLoading">Loading {ppu.ppu_id}…</div>}
                          {runtime?.error && <div className="ppuError">{runtime.error}</div>}
                          {runtime && !runtime.loading && !runtime.error && (
                            <div className="productionSitePrototypeGrid">
                              {runtime.sites.map(site => (
                                <article className={`productionSitePrototype site-${site.state} ${site.selected ? "selected" : ""}`} data-production-site={site.id} data-site-state={site.state} key={site.id}>
                                  <div className="prototypeSiteTop">
                                    <label>
                                      <input type="checkbox" aria-label={`${ppu.ppu_id} ${siteLabel(site.id)}`} checked={site.selected} disabled={batchRunning || !site.enabled} onChange={() => toggleSite(ppu.ppu_id, site.id)} />
                                      <b>{siteLabel(site.id)}</b>
                                    </label>
                                    <span>{site.operation ? operationCodes[site.operation] : "—"}</span>
                                  </div>
                                  <div className={`prototypeSiteLamp ${site.state}`}><i /></div>
                                  <strong>{site.state === "success" ? text.success : site.state === "failed" ? text.failed : site.state === "cancelled" ? text.cancelled : site.state === "running" ? text.running : text.ready}</strong>
                                  <div className="prototypeSiteProgress"><i style={{ width: `${Math.max(0, Math.min(100, site.progress))}%` }} /></div>
                                  <small>{site.state === "running" ? `${site.progress}%` : site.error ?? `${site.target ?? "—"} / ${site.interface ?? "—"}`}</small>
                                </article>
                              ))}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </>
              )}
            </section>

            <section className="productionPrototypeLog" aria-label={text.log}>
              <header><div><p>MOCK EXECUTION OBSERVABILITY</p><h2>{text.log}</h2></div><button type="button" onClick={() => setLogs([])}>{text.clearLog}</button></header>
              <div className="prototypeLogBody">
                {logs.length === 0 && <div className="prototypeEmptyLog">—</div>}
                {logs.map(entry => <div className={`prototypeLogRow level-${entry.level.toLowerCase()}`} key={entry.id}><span>{entry.time}</span><b>{entry.level}</b><code>{entry.text}</code></div>)}
              </div>
            </section>
          </>
        )}
      </section>
    </main>
  );
}
