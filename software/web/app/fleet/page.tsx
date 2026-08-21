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
  Operation,
  SiteSnapshot,
} from "../plasma-api";
import "./fleet.css";
import "./production-prototype.css";
import "./operator-feedback.css";

type SiteRunState = "ready" | "running" | "success" | "failed" | "cancelled";
type BatchState = "idle" | "running" | "cancelling" | "complete" | "partial" | "cancelled";
type SelectionMap = Record<string, Record<string, number[]>>;
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
type ActiveJob = {
  targetKey: string;
  targetApiBase: string;
  jobId: string;
};
type LogEntry = { id: number; time: string; level: "INFO" | "WARN" | "ERROR"; text: string };

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
    subtitle: "Facility → PPU → Site 並行批次",
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
    selectedFacilities: "Facilities",
    selectedPpus: "PPUs",
    selectedSites: "Sites",
    noSelection: "尚未選擇 FPS。",
    operations: "批次操作",
    image: "Programming Image (.bin)",
    imageHint: "Program / Verify 需要 Image Asset，最大 16 MiB。",
    execute: "執行批次",
    cancelAll: "取消批次",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    failed: "FAIL",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    complete: "COMPLETE",
    batch: "Batch",
    liveStatus: "Active FPS : 即時執行狀態",
    hierarchyHint: "依 Facility / PPU / Site 定位",
    log: "Production Prototype Log",
    clearLog: "清除 Log",
    imageTooLarge: "Programming Image 超過 16 MiB。",
    imageRequired: "Program / Verify 需要先選擇 Programming Image。",
    chooseOperation: "請至少選擇一個操作。",
    noSelectedSites: "目前 FPS 集合沒有可執行的 Site。",
    loadFailed: "PPU 狀態載入失敗",
  },
  "en-US": {
    eyebrow: "PRODUCTION MODE · MOCK PROTOTYPE",
    title: "Factory Production Console",
    subtitle: "Facility → PPU → Site concurrent batch execution",
    provider: "Mock PPU Provider",
    loading: "Connecting to Mock Provider…",
    offline: "Mock Provider is unavailable. Enable the Engineering Mock Provider on the Plasma Web REST Gateway.",
    selector: "FPS Selection",
    selectorHint: "Select Facilities, PPUs, and Sites. Active FPS changes only after confirmation.",
    clearAll: "Cancel all selections",
    selectAll: "Select all",
    apply: "Confirm selection",
    collapse: "Collapse selector",
    expand: "Expand selector",
    selectedOverview: "Selected FPS Overview",
    selectedFacilities: "Facilities",
    selectedPpus: "PPUs",
    selectedSites: "Sites",
    noSelection: "No FPS selected.",
    operations: "Batch Operations",
    image: "Programming Image (.bin)",
    imageHint: "Program / Verify requires an Image Asset, max 16 MiB.",
    execute: "Execute Batch",
    cancelAll: "Cancel Batch",
    ready: "READY",
    running: "RUNNING",
    success: "PASS",
    failed: "FAIL",
    cancelled: "CANCELLED",
    partial: "PARTIAL",
    complete: "COMPLETE",
    batch: "Batch",
    liveStatus: "Active FPS : Live Execution Status",
    hierarchyHint: "Locate by Facility / PPU / Site",
    log: "Production Prototype Log",
    clearLog: "Clear Log",
    imageTooLarge: "Programming Image exceeds 16 MiB.",
    imageRequired: "Program / Verify requires a Programming Image.",
    chooseOperation: "Select at least one operation.",
    noSelectedSites: "The active FPS set has no executable Site.",
    loadFailed: "PPU status load failed",
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

function runtimeFromStatus(snapshot: SiteSnapshot): SiteRuntime {
  return {
    id: snapshot.site_id,
    enabled: snapshot.enabled,
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
  const sites = runtime.sites;
  if (sites.length === 0) return "ready";
  if (sites.some(site => site.state === "running")) return "running";
  if (sites.every(site => site.state === "success")) return "success";
  if (sites.every(site => site.state === "cancelled")) return "cancelled";
  if (sites.some(site => site.state === "failed")) return "failed";
  if (sites.some(site => site.state === "success" || site.state === "cancelled")) return "partial";
  return "ready";
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

export default function FleetPage() {
  const { locale, t } = useI18n();
  const text = copy[locale];
  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [draftSelection, setDraftSelection] = useState<SelectionMap>({});
  const [activeSelection, setActiveSelection] = useState<SelectionMap>({});
  const [runtimes, setRuntimes] = useState<Record<string, PPURuntime>>({});
  const [selectedOperations, setSelectedOperations] = useState<Operation[]>([]);
  const [imageAsset, setImageAsset] = useState<File | null>(null);
  const [batchState, setBatchState] = useState<BatchState>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [selectorCollapsed, setSelectorCollapsed] = useState(false);

  const currentJobs = useRef<Map<string, ActiveJob>>(new Map());
  const cancelAllRequested = useRef(false);
  const cancelledTargets = useRef<Set<string>>(new Set());
  const logSequence = useRef(0);

  const appendLog = useCallback((textValue: string, level: LogEntry["level"] = "INFO") => {
    setLogs(current => [...current, {
      id: ++logSequence.current,
      time: nowTime(),
      level,
      text: textValue,
    }].slice(-500));
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
        setDraftSelection({});
        appendLog(`[PROVIDER] ${next.provider.toUpperCase()} · ${next.facility_count} Facilities · ${next.ppu_count} PPUs · ${next.site_count} Sites`);
      } catch (error) {
        if (stopped) return;
        const detail = error instanceof Error ? error.message : "Mock Provider unavailable";
        setProviderError(detail);
        setCatalog(null);
        appendLog(`[PROVIDER] unavailable · ${detail}`, "ERROR");
      }
    })();
    return () => { stopped = true; };
  }, [appendLog]);

  const batchRunning = batchState === "running" || batchState === "cancelling";
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
    return {
      facilities: activeCounts.facilities,
      ppus: activeCounts.ppus,
      sites: activeCounts.sites,
      running: sites.filter(site => site.state === "running").length,
      success: sites.filter(site => site.state === "success").length,
      failed: sites.filter(site => site.state === "failed").length,
      cancelled: sites.filter(site => site.state === "cancelled").length,
    };
  }, [activeCounts, runtimes]);

  const siteDensity = densityFor(summary.sites);

  const updateSite = useCallback((key: string, siteId: number, patch: Partial<SiteRuntime>) => {
    setRuntimes(current => {
      const runtime = current[key];
      if (!runtime) return current;
      return {
        ...current,
        [key]: { ...runtime, sites: runtime.sites.map(site => site.id === siteId ? { ...site, ...patch } : site) },
      };
    });
  }, []);

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
    const targets = catalog.facilities.flatMap(facility => facility.ppus.flatMap(target => {
      const siteIds = snapshot[facility.facility_id]?.[target.ppu_id] ?? [];
      if (siteIds.length === 0) return [];
      return [{ facility, target, siteIds, key: targetKey(facility.facility_id, target.ppu_id) }];
    }));

    setActiveSelection(snapshot);
    setBatchState("idle");
    cancelAllRequested.current = false;
    cancelledTargets.current.clear();
    currentJobs.current.clear();
    setRuntimes(Object.fromEntries(targets.map(item => [item.key, {
      facilityId: item.facility.facility_id,
      target: item.target,
      sites: [],
      loading: true,
    } satisfies PPURuntime])));
    appendLog(`[FPS] CONFIRM · ${selectionCounts(snapshot).facilities} Facilities · ${targets.length} PPUs · ${selectionCounts(snapshot).sites} Sites`);

    const results = await Promise.allSettled(targets.map(async item => {
      const targetBase = engineeringTargetApiBase(DEFAULT_API_BASE, item.facility.facility_id, item.target.ppu_id);
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
  }

  function toggleOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : [...current, operation]);
  }

  async function waitForTerminal(key: string, siteId: number, targetBase: string, jobId: string): Promise<SiteRunState> {
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      const job = await getJob(targetBase, jobId);
      const progress = Math.round(Number(job.progress_percent ?? 0));
      if (!terminalStates.has(job.state)) {
        updateSite(key, siteId, { state: "running", progress, operation: job.operation, jobId: job.job_id });
      }
      if (terminalStates.has(job.state)) {
        if (job.state === "success") return "success";
        if (job.state === "cancelled") return "cancelled";
        return "failed";
      }
      await delay(POLL_INTERVAL_MS);
    }
    throw new Error(`Job ${jobId} polling timed out`);
  }

  async function runSiteSequence(active: ActiveTarget, siteId: number, operations: Operation[]): Promise<SiteRunState> {
    const targetBase = engineeringTargetApiBase(DEFAULT_API_BASE, active.facility.facility_id, active.target.ppu_id);
    const cancellationRequested = () => cancelAllRequested.current || cancelledTargets.current.has(active.key);
    try {
      updateSite(active.key, siteId, { state: "running", progress: 0, error: undefined });
      for (const operation of operations) {
        if (cancellationRequested()) {
          updateSite(active.key, siteId, { state: "cancelled", progress: 0 });
          return "cancelled";
        }
        appendLog(`[JOB] START · ${active.facility.facility_id} · ${active.target.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`);
        const job = await startJob(targetBase, {
          siteId,
          operation,
          assetFile: imageAsset,
          engineeringSessionId: sessionId ?? undefined,
          offset: 0,
          length: 256,
          submissionGuard: () => !cancellationRequested(),
        });
        const jobKey = `${active.key}:${siteId}`;
        currentJobs.current.set(jobKey, { targetKey: active.key, targetApiBase: targetBase, jobId: job.job_id });
        updateSite(active.key, siteId, { state: "running", progress: Math.round(Number(job.progress_percent ?? 0)), operation, jobId: job.job_id });
        if (cancellationRequested()) await cancelJob(targetBase, job.job_id).catch(() => undefined);
        const terminal = await waitForTerminal(active.key, siteId, targetBase, job.job_id);
        currentJobs.current.delete(jobKey);
        if (terminal !== "success") {
          updateSite(active.key, siteId, { state: terminal, progress: terminal === "cancelled" ? 100 : 0 });
          appendLog(
            `[JOB] ${terminal.toUpperCase()} · ${active.target.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`,
            terminal === "failed" ? "ERROR" : "WARN",
          );
          return terminal;
        }
        appendLog(`[JOB] PASS · ${active.target.ppu_id} · ${siteLabel(siteId)} · ${operation.toUpperCase()}`);
      }
      updateSite(active.key, siteId, { state: "success", progress: 100 });
      return "success";
    } catch (error) {
      if (cancellationRequested()) {
        updateSite(active.key, siteId, { state: "cancelled", progress: 0 });
        appendLog(`[JOB] CANCELLED · ${active.target.ppu_id} · ${siteLabel(siteId)}`, "WARN");
        return "cancelled";
      }
      const detail = error instanceof Error ? error.message : "Job failed";
      updateSite(active.key, siteId, { state: "failed", progress: 0, error: detail });
      appendLog(`[JOB] FAIL · ${active.target.ppu_id} · ${siteLabel(siteId)} · ${detail}`, "ERROR");
      return "failed";
    }
  }

  async function executeBatch() {
    if (batchRunning || activeTargets.length === 0) return;
    const operations = orderedOperations(selectedOperations);
    if (operations.length === 0) {
      appendLog(`[BAT] BLOCKED · ${text.chooseOperation}`, "WARN");
      return;
    }
    if (operations.some(operation => operation === "program" || operation === "verify") && !imageAsset) {
      appendLog(`[BAT] BLOCKED · ${text.imageRequired}`, "WARN");
      return;
    }
    const selected = activeTargets.flatMap(active => {
      const runtime = runtimes[active.key];
      return (runtime?.sites ?? []).filter(site => site.enabled).map(site => ({ active, siteId: site.id }));
    });
    if (selected.length === 0) {
      appendLog(`[BAT] BLOCKED · ${text.noSelectedSites}`, "WARN");
      return;
    }

    cancelAllRequested.current = false;
    cancelledTargets.current.clear();
    currentJobs.current.clear();
    setBatchState("running");
    setRuntimes(current => Object.fromEntries(Object.entries(current).map(([key, runtime]) => [key, {
      ...runtime,
      sites: runtime.sites.map(site => ({ ...site, state: "ready" as const, progress: 0, jobId: undefined, error: undefined })),
    }])) as Record<string, PPURuntime>);
    appendLog(`[BAT] START · ${summary.facilities} Facilities · ${activeTargets.length} PPUs · ${selected.length} Sites · ${operations.map(operation => operation.toUpperCase()).join(" → ")}`);

    const results = await Promise.allSettled(selected.map(item => runSiteSequence(item.active, item.siteId, operations)));
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
      appendLog(`[BAT] PARTIAL · success: ${pass} · failed: ${failed} · cancelled: ${cancelled}`, failed ? "ERROR" : "WARN");
    }
  }

  async function cancelActiveJobs(filterTargetKey?: string) {
    const jobs = [...currentJobs.current.values()].filter(job => !filterTargetKey || job.targetKey === filterTargetKey);
    await Promise.allSettled(jobs.map(job => cancelJob(job.targetApiBase, job.jobId)));
  }

  async function cancelBatch() {
    if (!batchRunning) return;
    cancelAllRequested.current = true;
    setBatchState("cancelling");
    appendLog("[BAT] CANCEL REQUESTED", "WARN");
    await cancelActiveJobs();
  }

  async function cancelPPU(key: string) {
    if (!batchRunning) return;
    cancelledTargets.current.add(key);
    appendLog(`[PPU] CANCEL REQUESTED · ${key}`, "WARN");
    await cancelActiveJobs(key);
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
                  <header className="fpsSelectorHead">
                    <div><h2>{text.selector}</h2><span>{text.selectorHint}</span></div>
                  </header>

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
                    {draftCounts.sites === 0 ? <p>{text.noSelection}</p> : (
                      <div className="fpsSelectionChips">
                        {catalog.facilities.flatMap(facility => facility.ppus.flatMap(ppu => {
                          const siteIds = selectedSiteIds(facility.facility_id, ppu.ppu_id);
                          if (siteIds.length === 0) return [];
                          return [<span key={`${facility.facility_id}-${ppu.ppu_id}`}>{facility.display_name} · {ppu.display_name} · {siteIds.length}S</span>];
                        }))}
                      </div>
                    )}
                  </section>
                </>
              )}
            </aside>

            <section className="productionMainPanel">
              <section className="prototypeTopologySummary" aria-label="Mock topology summary">
                <article><small>Facilities</small><b>{catalog.facility_count}</b></article>
                <article><small>PPUs</small><b>{catalog.ppu_count}</b></article>
                <article><small>{text.selectedSites}</small><b>{summary.sites}</b><span>{summary.facilities} F / {summary.ppus} P</span></article>
                <article className="runtimeSummary"><small>PASS</small><b>{summary.success}</b><span>FAIL {summary.failed} · RUN {summary.running} · CAN {summary.cancelled}</span></article>
              </section>

              <section className="productionBatchToolbar" aria-label="Batch operation toolbar">
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
                  <div className={`batchState batch-${batchState}`}><small>{text.batch}</small><b>{batchLabel}</b></div>
                  <button type="button" className="executeBatchButton" onClick={() => void executeBatch()} disabled={batchRunning || activeCounts.sites === 0}>{text.execute}</button>
                  <button type="button" className="cancelBatchButton" onClick={() => void cancelBatch()} disabled={!batchRunning}>{text.cancelAll}</button>
                </div>
              </section>

              <section className={`productionRuntimeBoard density-${siteDensity}`} aria-label={text.liveStatus}>
                <header className="runtimeBoardHead">
                  <div><h2>{text.liveStatus}</h2><span>{text.hierarchyHint}</span></div>
                  <div className="runtimeLegend">
                    <span><i className="ready" /> READY</span><span><i className="running" /> RUNNING</span><span><i className="success" /> PASS</span><span><i className="failed" /> FAIL</span><span><i className="cancelled" /> CANCELLED</span>
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
                                    <button type="button" className="cancelPpuButton" onClick={() => void cancelPPU(active.key)} disabled={!batchRunning}>Cancel PPU</button>
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
                                          key={site.id}
                                          title={`${group.facility.display_name} / ${active.target.display_name} / ${siteLabel(site.id)}`}
                                        >
                                          <b>{siteLabel(site.id)}</b>
                                          <div className={`prototypeSiteLamp ${site.state}`}><i /></div>
                                          <strong>{site.state === "success" ? text.success : site.state === "failed" ? text.failed : site.state === "cancelled" ? text.cancelled : site.state === "running" ? text.running : text.ready}</strong>
                                          {site.operation && <small>{operationCodes[site.operation]} · {t(`operation.${site.operation}`)}{site.state === "running" ? ` · ${site.progress}%` : ""}</small>}
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