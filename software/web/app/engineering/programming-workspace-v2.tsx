"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ICPickerField } from "../devices/ic-picker-field";
import type { DeviceSearchResult } from "../device-catalog-api";
import {
  cancelJob,
  engineeringTargetApiBase,
  getEngineeringTargets,
  getJob,
  getPPUStatus,
  readDownloadUrl,
  startJob,
  type AssetTransferEvent,
  type EngineeringTargetCatalog,
  type JobSnapshot,
  type JobState,
  type Operation,
  type PPUSnapshot,
  type SiteSnapshot,
} from "../plasma-api";
import { useWorkspaceSession } from "../workspace-session";
import "../fleet/programming/production-programming.css";
import "./programming-workspace-v2.css";

const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = { erase: "E", program: "P", verify: "V", read: "R" };
const terminalJobStates = new Set<JobState>(["success", "failed", "error", "cancelled", "timeout", "aborted"]);
const POLL_MS = 500;
const MAX_IMAGE_BYTES = 16 * 1024 * 1024;

type RuntimeState = "idle" | "queued" | "running" | "success" | "faulted" | "error" | "cancelled" | "stopped" | "disabled";
type EventLevel = "info" | "warn" | "error";
type EventEntry = { id: number; time: string; text: string; level: EventLevel };
type RuntimeSite = SiteSnapshot & {
  runtimeState: RuntimeState;
  progress: number;
  operation?: Operation;
  jobId?: string;
  error?: string;
  outputFile?: string;
};

type StopPolicy = { kind: "never" } | { kind: "failed_sites"; threshold: number };

function nowTime(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function initialRuntime(site: SiteSnapshot): RuntimeSite {
  const running = Boolean(site.current_job_id) || site.state === "running" || site.state === "queued";
  return {
    ...site,
    runtimeState: site.enabled ? (running ? "running" : "idle") : "disabled",
    progress: 0,
    jobId: site.current_job_id ?? undefined,
  };
}

function runtimeFromJob(site: RuntimeSite, job: JobSnapshot): RuntimeSite {
  let runtimeState: RuntimeState;
  if (job.state === "success") runtimeState = "success";
  else if (job.state === "failed") runtimeState = "faulted";
  else if (job.state === "cancelled") runtimeState = "cancelled";
  else if (job.state === "error" || job.state === "timeout" || job.state === "aborted") runtimeState = "error";
  else runtimeState = job.state === "queued" ? "queued" : "running";
  return {
    ...site,
    runtimeState,
    progress: Math.round(job.progress_percent ?? 0),
    operation: job.operation,
    jobId: job.job_id,
    error: job.result?.error?.message,
    outputFile: job.result?.output_files?.[0],
  };
}

function resultLabel(state: RuntimeState): string {
  if (state === "success") return "PASS";
  if (state === "faulted") return "FAIL";
  if (state === "error") return "ERROR";
  if (state === "cancelled") return "CANCELLED";
  if (state === "stopped") return "STOPPED";
  return "—";
}

function cycleTimeLabel(startedAt: number | null, finishedAt: number | null, nowTick: number): string {
  if (startedAt === null) return "--";
  const end = finishedAt ?? nowTick;
  return `${Math.max(0, (end - startedAt) / 1000).toFixed(1)}s`;
}

function targetDeviceLabel(device: DeviceSearchResult | null, fallback = "—"): string {
  return device?.icpn ?? device?.identifier ?? fallback;
}

export default function ProgrammingWorkspaceV2() {
  const {
    hydrated,
    apiBase,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    programmingImage,
    setProgrammingImage,
    emodeSelection,
    setEmodeSelection,
    emodeSiteIds,
    setEmodeSiteIds,
    emodeOperations,
    setEmodeOperations,
    emodeReadOffset,
    setEmodeReadOffset,
    emodeReadLength,
    setEmodeReadLength,
  } = useWorkspaceSession();

  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [ppu, setPPU] = useState<PPUSnapshot | null>(null);
  const [sites, setSites] = useState<RuntimeSite[]>([]);
  const [targetDevice, setTargetDevice] = useState<DeviceSearchResult | null>(null);
  const [repeatCount, setRepeatCount] = useState("1");
  const [retryLimit, setRetryLimit] = useState("3");
  const [stopPolicy, setStopPolicy] = useState<StopPolicy>({ kind: "never" });
  const [apiDraft, setApiDraft] = useState(apiBase);
  const [connection, setConnection] = useState<"connecting" | "online" | "offline">("connecting");
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchAborting, setBatchAborting] = useState(false);
  const [directBusy, setDirectBusy] = useState(false);
  const [batchStartedAt, setBatchStartedAt] = useState<number | null>(null);
  const [batchFinishedAt, setBatchFinishedAt] = useState<number | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [refreshGeneration, setRefreshGeneration] = useState(0);

  const eventSequence = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const activeJobs = useRef<Map<number, string>>(new Map());
  const abortRequested = useRef(false);
  const thresholdStopRequested = useRef(false);
  const selectedTargetKey = useRef<string | null>(null);
  const emodeSiteIdsRef = useRef<number[] | null>(emodeSiteIds);
  const emodeSelectionRef = useRef(emodeSelection);
  const nowTickRef = useRef(nowTick);

  const facility = catalog?.facilities.find(item => item.facility_id === emodeSelection.facilityId) ?? null;
  const selectedPPU = facility?.ppus.find(item => item.ppu_id === emodeSelection.ppuId) ?? null;
  const selectedSiteIds = emodeSiteIds ?? [];
  const selectedSites = sites.filter(site => selectedSiteIds.includes(site.site_id));
  const targetApiBase = emodeSelection.facilityId && emodeSelection.ppuId
    ? engineeringTargetApiBase(apiBase, emodeSelection.facilityId, emodeSelection.ppuId)
    : null;
  const hasRunningSite = sites.some(site => site.runtimeState === "queued" || site.runtimeState === "running");
  const executionLocked = batchRunning || directBusy || hasRunningSite;
  const syntheticMockImageAvailable = selectedPPU?.provider === "mock";
  const repeatValue = Number(repeatCount);
  const retryValue = Number(retryLimit);
  const readOffset = Number(emodeReadOffset);
  const readLength = Number(emodeReadLength);
  const stopPolicyValue = stopPolicy.kind === "never" ? "never" : String(stopPolicy.threshold);
  const requiresImage = emodeOperations.some(operation => operation === "program" || operation === "verify");
  const imageTooLarge = Boolean(programmingImage && programmingImage.size > MAX_IMAGE_BYTES);
  const unsupportedImage = Boolean(programmingImage && !programmingImage.name.toLowerCase().endsWith(".bin"));
  const policyValid = Number.isSafeInteger(repeatValue) && repeatValue >= 1 && repeatValue <= 10000
    && Number.isSafeInteger(retryValue) && retryValue >= 0 && retryValue <= 20;
  const readValid = Number.isSafeInteger(readOffset) && readOffset >= 0 && Number.isSafeInteger(readLength) && readLength > 0;

  const appendEvent = useCallback((text: string, level: EventLevel = "info") => {
    setEvents(current => [{ id: ++eventSequence.current, time: nowTime(), text, level }, ...current].slice(0, 20));
  }, []);

  useEffect(() => {
    emodeSiteIdsRef.current = emodeSiteIds;
  }, [emodeSiteIds]);

  useEffect(() => {
    emodeSelectionRef.current = emodeSelection;
  }, [emodeSelection]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = Date.now();
      nowTickRef.current = next;
      setNowTick(next);
    }, 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;
    void (async () => {
      try {
        await ensureEngineeringSession(apiBase);
        const nextCatalog = await getEngineeringTargets(apiBase);
        if (cancelled) return;
        setCatalog(nextCatalog);
        const selection = emodeSelectionRef.current;
        const currentFacility = nextCatalog.facilities.find(item => item.facility_id === selection.facilityId);
        const currentPpu = currentFacility?.ppus.find(item => item.ppu_id === selection.ppuId);
        if (!currentFacility || !currentPpu) {
          const firstFacility = nextCatalog.facilities[0];
          const nextSelection = {
            facilityId: firstFacility?.facility_id ?? "",
            ppuId: firstFacility?.ppus[0]?.ppu_id ?? "",
          };
          emodeSelectionRef.current = nextSelection;
          emodeSiteIdsRef.current = null;
          setEmodeSelection(nextSelection);
          setEmodeSiteIds(null);
        }
        setConnection("online");
        setError(null);
        appendEvent(`Connected to ${nextCatalog.provider} Engineering topology.`);
      } catch (loadError) {
        if (cancelled) return;
        setConnection("offline");
        setError(loadError instanceof Error ? loadError.message : "Engineering topology unavailable.");
      }
    })();
    return () => { cancelled = true; };
  }, [apiBase, appendEvent, ensureEngineeringSession, hydrated, refreshGeneration, setEmodeSelection, setEmodeSiteIds]);

  useEffect(() => {
    if (!catalog || !targetApiBase || !selectedPPU) return;
    let cancelled = false;
    void getPPUStatus(targetApiBase)
      .then(status => {
        if (cancelled) return;
        const nextSites = status.sites.map(initialRuntime);
        setPPU(status.ppu ?? null);
        setSites(nextSites);
        const key = `${emodeSelection.facilityId}/${emodeSelection.ppuId}`;
        const existing = emodeSiteIdsRef.current;
        const validExisting = selectedTargetKey.current === key && existing !== null
          ? existing.filter(siteId => nextSites.some(site => site.site_id === siteId && site.enabled))
          : [];
        const nextSelection = validExisting.length > 0 || (selectedTargetKey.current === key && existing?.length === 0)
          ? validExisting
          : nextSites.filter(site => site.enabled).map(site => site.site_id);
        emodeSiteIdsRef.current = nextSelection;
        setEmodeSiteIds(nextSelection);
        selectedTargetKey.current = key;
        appendEvent(`Loaded ${facility?.display_name ?? emodeSelection.facilityId} / ${selectedPPU.display_name}.`);
      })
      .catch(loadError => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "PPU status unavailable.");
      });
    return () => { cancelled = true; };
  }, [appendEvent, catalog, emodeSelection.facilityId, emodeSelection.ppuId, facility?.display_name, refreshGeneration, selectedPPU, setEmodeSiteIds, targetApiBase]);

  const counts = useMemo(() => {
    const pass = selectedSites.filter(site => site.runtimeState === "success").length;
    const fail = selectedSites.filter(site => site.runtimeState === "faulted" || site.runtimeState === "error").length;
    const running = selectedSites.filter(site => site.runtimeState === "queued" || site.runtimeState === "running").length;
    const stopped = selectedSites.filter(site => site.runtimeState === "cancelled" || site.runtimeState === "stopped").length;
    const completed = pass + fail;
    return {
      pass,
      fail,
      running,
      stopped,
      totalIc: completed > 0 ? completed : selectedSiteIds.length,
      yieldPercent: completed > 0 ? (pass / completed) * 100 : 0,
    };
  }, [selectedSiteIds.length, selectedSites]);

  function chooseFacility(facilityId: string) {
    if (executionLocked || !catalog) return;
    const nextFacility = catalog.facilities.find(item => item.facility_id === facilityId);
    const nextSelection = { facilityId, ppuId: nextFacility?.ppus[0]?.ppu_id ?? "" };
    emodeSelectionRef.current = nextSelection;
    emodeSiteIdsRef.current = null;
    setEmodeSelection(nextSelection);
    setEmodeSiteIds(null);
    selectedTargetKey.current = null;
    setTargetDevice(null);
    setError(null);
  }

  function choosePpu(ppuId: string) {
    if (executionLocked) return;
    const nextSelection = { facilityId: emodeSelection.facilityId, ppuId };
    emodeSelectionRef.current = nextSelection;
    emodeSiteIdsRef.current = null;
    setEmodeSelection(nextSelection);
    setEmodeSiteIds(null);
    selectedTargetKey.current = null;
    setTargetDevice(null);
    setError(null);
  }

  function toggleSite(siteId: number) {
    if (executionLocked) return;
    setEmodeSiteIds(current => {
      const values = current ?? [];
      const next = values.includes(siteId)
        ? values.filter(id => id !== siteId)
        : [...values, siteId].sort((a, b) => a - b);
      emodeSiteIdsRef.current = next;
      return next;
    });
  }

  function toggleOperation(operation: Operation) {
    if (executionLocked) return;
    setEmodeOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : operationOrder.filter(item => current.includes(item) || item === operation));
  }

  function updateSite(siteId: number, updater: (site: RuntimeSite) => RuntimeSite) {
    setSites(current => current.map(site => site.site_id === siteId ? updater(site) : site));
  }

  function logAssetEvent(event: AssetTransferEvent) {
    const shortSha = `${event.asset_sha256.slice(0, 12)}…`;
    if (event.kind === "cache_hit") appendEvent(`Image cache hit · ${event.asset_name} · ${shortSha}`);
    else if (event.kind === "upload_start") appendEvent(`Uploading Image · ${event.asset_name} · ${shortSha}`);
    else if (event.kind === "upload_complete") appendEvent(`Image upload complete · ${event.asset_name} · ${shortSha}`);
  }

  async function waitTerminal(job: JobSnapshot): Promise<JobSnapshot> {
    if (!targetApiBase) throw new Error("No Engineering PPU selected.");
    let current = job;
    for (let attempt = 0; attempt < 600; attempt += 1) {
      current = await getJob(targetApiBase, current.job_id);
      updateSite(current.site_id, site => runtimeFromJob(site, current));
      if (terminalJobStates.has(current.state)) return current;
      await new Promise(resolve => window.setTimeout(resolve, POLL_MS));
    }
    throw new Error(`${job.job_id} polling timeout`);
  }

  async function runJob(siteId: number, operation: Operation): Promise<JobSnapshot> {
    if (!targetApiBase) throw new Error("No Engineering PPU selected.");
    const site = sites.find(item => item.site_id === siteId);
    if (!site?.enabled) throw new Error(`${siteLabel(siteId)} is disabled.`);
    const usesImage = operation === "program" || operation === "verify";
    if (usesImage && !programmingImage && !syntheticMockImageAvailable) throw new Error("Program/Verify requires a Programming Image.");
    if (usesImage && (imageTooLarge || unsupportedImage)) throw new Error("Engineering currently accepts binary Programming Image (.bin) up to 16 MiB.");
    if (operation === "read" && !readValid) throw new Error("READ offset/length is invalid.");

    const sessionId = usesImage ? (engineeringSessionId ?? await ensureEngineeringSession(apiBase)) : undefined;
    const synthetic = usesImage && !programmingImage && syntheticMockImageAvailable;
    const accepted = await startJob(targetApiBase, {
      siteId,
      operation,
      assetFile: usesImage ? programmingImage : null,
      engineeringSessionId: sessionId,
      allowSyntheticMockImage: synthetic,
      offset: operation === "read" ? readOffset : undefined,
      length: operation === "read" ? readLength : undefined,
      targetDevice: targetDevice ? { vendor: targetDevice.vendor, identifier: targetDevice.identifier } : undefined,
      onAssetEvent: logAssetEvent,
    });
    activeJobs.current.set(siteId, accepted.job_id);
    updateSite(siteId, current => ({ ...current, runtimeState: "queued", progress: 0, operation, jobId: accepted.job_id, error: undefined, outputFile: undefined }));
    appendEvent(`${siteLabel(siteId)} ${operation.toUpperCase()} accepted · ${accepted.job_id.slice(-8)}.`);
    try {
      return await waitTerminal(accepted);
    } finally {
      activeJobs.current.delete(siteId);
    }
  }

  async function cancelActiveJobs() {
    if (!targetApiBase) return;
    const jobs = [...activeJobs.current.entries()];
    await Promise.allSettled(jobs.map(async ([siteId, jobId]) => {
      try {
        await cancelJob(targetApiBase, jobId);
        appendEvent(`${siteLabel(siteId)} cancel requested.`, "warn");
      } catch (cancelError) {
        appendEvent(`${siteLabel(siteId)} cancel failed · ${cancelError instanceof Error ? cancelError.message : "unknown error"}.`, "error");
      }
    }));
  }

  async function runSingleSite(siteId: number, operation: Operation) {
    if (executionLocked) return;
    setDirectBusy(true);
    setError(null);
    setBatchStartedAt(nowTickRef.current);
    setBatchFinishedAt(null);
    try {
      const result = await runJob(siteId, operation);
      appendEvent(`${siteLabel(siteId)} ${operation.toUpperCase()} ${result.state.toUpperCase()}.`, result.state === "success" ? "info" : "error");
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : "Site operation failed.";
      setError(message);
      updateSite(siteId, site => ({ ...site, runtimeState: "error", error: message }));
      appendEvent(`${siteLabel(siteId)} ${operation.toUpperCase()} failed · ${message}.`, "error");
    } finally {
      setDirectBusy(false);
      setBatchFinishedAt(nowTickRef.current);
    }
  }

  async function runBatch() {
    if (executionLocked) return;
    if (selectedSiteIds.length === 0) { setError("Select at least one Site."); return; }
    if (emodeOperations.length === 0) { setError("Select at least one E/P/V/R operation."); return; }
    if (!policyValid) { setError("Batch Policy is invalid."); return; }
    if (requiresImage && !programmingImage && !syntheticMockImageAvailable) { setError("Program/Verify requires a Programming Image."); return; }
    if (imageTooLarge || unsupportedImage) { setError("Engineering currently accepts binary Programming Image (.bin) up to 16 MiB."); return; }
    if (emodeOperations.includes("read") && !readValid) { setError("READ offset/length is invalid."); return; }

    setError(null);
    setBatchRunning(true);
    setBatchAborting(false);
    setBatchStartedAt(nowTickRef.current);
    setBatchFinishedAt(null);
    abortRequested.current = false;
    thresholdStopRequested.current = false;
    let finalFailures = 0;
    const ordered = operationOrder.filter(operation => emodeOperations.includes(operation));
    appendEvent(`Batch start · ${selectedSiteIds.map(siteLabel).join(", ")} · ${ordered.map(operation => operationCodes[operation]).join("→")} · repeat ${repeatValue} · retry ${retryValue}.`);

    try {
      await Promise.all(selectedSiteIds.map(async siteId => {
        for (let round = 1; round <= repeatValue; round += 1) {
          for (const operation of ordered) {
            if (abortRequested.current || thresholdStopRequested.current) {
              updateSite(siteId, site => ({ ...site, runtimeState: abortRequested.current ? "cancelled" : "stopped" }));
              return;
            }
            let succeeded = false;
            for (let attempt = 0; attempt <= retryValue; attempt += 1) {
              if (abortRequested.current || thresholdStopRequested.current) return;
              try {
                const result = await runJob(siteId, operation);
                if (result.state === "success") {
                  succeeded = true;
                  break;
                }
                if (result.state === "cancelled") {
                  updateSite(siteId, site => ({ ...site, runtimeState: abortRequested.current ? "cancelled" : "stopped" }));
                  return;
                }
                if (result.state !== "failed") throw new Error(result.result?.error?.message ?? result.state.toUpperCase());
                if (attempt < retryValue) {
                  appendEvent(`${siteLabel(siteId)} retry ${attempt + 1}/${retryValue} · ${operation.toUpperCase()}.`, "warn");
                  continue;
                }
              } catch (jobError) {
                if (abortRequested.current || thresholdStopRequested.current) return;
                if (attempt < retryValue) {
                  appendEvent(`${siteLabel(siteId)} retry ${attempt + 1}/${retryValue} · ${operation.toUpperCase()} · ${jobError instanceof Error ? jobError.message : "failed"}.`, "warn");
                  continue;
                }
              }
              finalFailures += 1;
              updateSite(siteId, site => ({ ...site, runtimeState: "faulted" }));
              appendEvent(`${siteLabel(siteId)} FAIL · retry exhausted.`, "error");
              if (stopPolicy.kind === "failed_sites" && finalFailures >= stopPolicy.threshold) {
                thresholdStopRequested.current = true;
                appendEvent(`Stop Policy triggered · ${finalFailures} failed Site(s).`, "warn");
                await cancelActiveJobs();
              }
              return;
            }
            if (!succeeded) return;
          }
        }
        updateSite(siteId, site => ({ ...site, runtimeState: "success", progress: 100 }));
      }));
      appendEvent(abortRequested.current ? "Batch aborted." : thresholdStopRequested.current ? "Batch stopped by policy." : "Batch complete.", abortRequested.current || thresholdStopRequested.current ? "warn" : "info");
    } finally {
      setBatchRunning(false);
      setBatchAborting(false);
      setBatchFinishedAt(nowTickRef.current);
    }
  }

  async function abortBatch() {
    if (!batchRunning || batchAborting) return;
    abortRequested.current = true;
    setBatchAborting(true);
    appendEvent("Abort requested for Engineering Batch.", "warn");
    await cancelActiveJobs();
  }

  async function reconnect(event: FormEvent) {
    event.preventDefault();
    if (executionLocked) return;
    setConnection("connecting");
    setError(null);
    try {
      const normalized = setApiBase(apiDraft);
      setApiDraft(normalized);
      await restartEngineeringSession(normalized);
      setRefreshGeneration(current => current + 1);
      setConnection("online");
      appendEvent(`Reconnected to ${normalized}.`);
    } catch (connectError) {
      setConnection("offline");
      setError(connectError instanceof Error ? connectError.message : "Reconnect failed.");
    }
  }

  const selectedTargetFallback = selectedSites[0]?.target ?? sites[0]?.target ?? "—";

  return (
    <section className="engineeringProgrammingV2" aria-label="Engineering Programming workspace">
      <main className="productionProgrammingV2">
        <header className="productionProgrammingHeader engineeringProgrammingV2Header">
          <h1>SINGLE PPU PROGRAMMING</h1>
          <form className={`engineeringGateway ${connection}`} onSubmit={reconnect}>
            <span className="onlineDot" />
            <input aria-label="Engineering Gateway URL" value={apiDraft} disabled={executionLocked} onChange={event => setApiDraft(event.target.value)} />
            <button type="submit" disabled={executionLocked}>Connect</button>
            <b>EMode</b>
          </form>
        </header>

        <section className="productionProgrammingKpis" aria-label="Engineering programming KPIs">
          <article><small>SITES</small><b>{selectedSiteIds.length}</b></article>
          <article><small>TOTAL IC</small><b>{counts.totalIc}</b></article>
          <article><small>RUNNING</small><b>{counts.running}</b></article>
          <article data-kpi="pass"><small>PASS</small><b>{counts.pass}</b></article>
          <article data-kpi="fail"><small>FAIL</small><b>{counts.fail}</b></article>
          <article data-kpi="yield"><small>YIELD</small><b>{counts.yieldPercent.toFixed(1)}%</b></article>
          <article><small>CYCLE TIME</small><b>{cycleTimeLabel(batchStartedAt, batchFinishedAt, nowTick)}</b></article>
        </section>

        <div className="productionProgrammingWorkflow">
          <section className="productionProgrammingCard targetingCard">
            <header>SYSTEM SETUP &amp; TARGETING</header>
            <div className="cardBody">
              <h2>SERVER TOPOLOGY</h2>
              <label className="workflowField">
                <span>Select Facility:</span>
                <select aria-label="Engineering Facility" disabled={executionLocked || !catalog} value={emodeSelection.facilityId} onChange={event => chooseFacility(event.target.value)}>
                  {(catalog?.facilities ?? []).map(item => <option key={item.facility_id} value={item.facility_id}>{item.display_name}</option>)}
                </select>
              </label>
              <label className="workflowField">
                <span>Select PPU:</span>
                <select aria-label="Engineering PPU" disabled={executionLocked || !facility} value={emodeSelection.ppuId} onChange={event => choosePpu(event.target.value)}>
                  {(facility?.ppus ?? []).map(item => <option key={item.ppu_id} value={item.ppu_id}>{item.display_name} - {item.site_count} Sites</option>)}
                </select>
              </label>

              <div className="targetSitesSection" aria-label="Engineering Site selection">
                <h2>TARGET SITES</h2>
                {sites.map(site => (
                  <label className="targetSiteRow" key={site.site_id}>
                    <input aria-label={`選取 SITE ${site.site_id}`} type="checkbox" checked={selectedSiteIds.includes(site.site_id)} disabled={executionLocked || !site.enabled} onChange={() => toggleSite(site.site_id)} />
                    <b>{siteLabel(site.site_id)}</b>
                    <span className="siteStatePill" data-state={site.runtimeState}>{site.runtimeState.toUpperCase()}</span>
                  </label>
                ))}
              </div>

              <div className="engineeringPpuIdentityV2" aria-label="Selected Engineering PPU">
                <b>{facility?.display_name ?? "—"} / {selectedPPU?.display_name ?? "—"}</b>
                <small>{ppu?.ppu_id ?? selectedPPU?.ppu_id ?? "—"} · {ppu?.site_count ?? selectedPPU?.site_count ?? 0} Sites · {ppu?.model ?? selectedPPU?.model ?? "—"}</small>
              </div>
              <div className="topologyFoot"><b>SERVER SOURCE OF TRUTH</b> · System Topology: {catalog?.facility_count ?? 0} Facilities | {catalog?.ppu_count ?? 0} PPUs | {catalog?.site_count ?? 0} Sites</div>
            </div>
          </section>

          <div className="productionProgrammingRight">
            <section className="productionProgrammingCard programmingJobCard">
              <header>PROGRAMMING JOB</header>
              <div className="cardBody programmingJobBody">
                <div className="jobRow">
                  <strong>1. Target IC</strong>
                  <ICPickerField apiBase={apiBase} value={targetDevice} onChange={setTargetDevice} disabled={executionLocked} placeholder={`Search ICPN / IC identifier... (${selectedTargetFallback})`} />
                </div>

                <div className="jobRow">
                  <strong>2. Programming Image</strong>
                  <div className="imageField">
                    <span title={programmingImage?.name}>{programmingImage?.name ?? (syntheticMockImageAvailable ? "Mock Synthetic Image or select .bin..." : "Select programming image (.bin)...")}</span>
                    <button type="button" disabled={executionLocked} onClick={() => fileInput.current?.click()}>Browse...</button>
                    <input ref={fileInput} aria-label="Engineering Programming Image Asset file" type="file" hidden accept=".bin,application/octet-stream" disabled={executionLocked} onChange={event => setProgrammingImage(event.target.files?.[0] ?? null)} />
                  </div>
                </div>

                <div className="jobRow operationsRow">
                  <strong>3. Operations</strong>
                  <div className="operationChecks" role="group" aria-label="Engineering batch operations">
                    {operationOrder.map(operation => (
                      <label key={operation} title={operation}>
                        <input aria-label={`Engineering batch ${operation}`} type="checkbox" disabled={executionLocked} checked={emodeOperations.includes(operation)} onChange={() => toggleOperation(operation)} />
                        <span>{operationCodes[operation]}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="jobRow batchPolicyRow engineeringPolicyRow">
                  <strong>4. Batch Policy</strong>
                  <label className="repeatField">Repeat: <input aria-label="Repeat" type="number" min="1" max="10000" disabled={executionLocked} value={repeatCount} onChange={event => setRepeatCount(event.target.value)} /></label>
                  <label className="engineeringRetryField">Retry: <input aria-label="Site Retry Limit" type="number" min="0" max="20" disabled={executionLocked} value={retryLimit} onChange={event => setRetryLimit(event.target.value)} /></label>
                  <label className="stopPolicyField">Stop Policy:
                    <select aria-label="Stop Policy" disabled={executionLocked || selectedSiteIds.length === 0} value={stopPolicyValue} onChange={event => setStopPolicy(event.target.value === "never" ? { kind: "never" } : { kind: "failed_sites", threshold: Number(event.target.value) })}>
                      <option value="never">Never</option>
                      {selectedSiteIds.map((_, index) => <option key={index + 1} value={index + 1}>{index + 1} Fail</option>)}
                    </select>
                  </label>
                </div>

                {emodeOperations.includes("read") && (
                  <div className="jobRow engineeringReadRow">
                    <strong>READ Parameters</strong>
                    <label>Offset <input aria-label="Engineering READ offset" type="number" min="0" value={emodeReadOffset} disabled={executionLocked} onChange={event => setEmodeReadOffset(event.target.value)} /></label>
                    <label>Length <input aria-label="Engineering READ length" type="number" min="1" value={emodeReadLength} disabled={executionLocked} onChange={event => setEmodeReadLength(event.target.value)} /></label>
                  </div>
                )}

                {(error || !policyValid || imageTooLarge || unsupportedImage) && (
                  <div className="programmingGuard" role="alert">{error ?? (!policyValid
                    ? "Batch Policy is invalid."
                    : imageTooLarge
                      ? "Programming Image exceeds the Engineering 16 MiB limit."
                      : "Engineering currently supports binary Programming Image (.bin) only.")}</div>
                )}

                <div className="programmingActions">
                  <button className="startProgramming" type="button" disabled={executionLocked || selectedSiteIds.length === 0 || emodeOperations.length === 0 || !policyValid || imageTooLarge || unsupportedImage || (requiresImage && !programmingImage && !syntheticMockImageAvailable)} onClick={() => void runBatch()}>▶ START PROGRAMMING</button>
                  <button className="abortProgramming" type="button" disabled={!batchRunning || batchAborting} onClick={() => void abortBatch()}>■ ABORT</button>
                </div>
              </div>
            </section>

            <section className="productionProgrammingCard progressMonitor">
              <header>LIVE PROGRESS MONITOR</header>
              <div>Total selected: {selectedSiteIds.length} | Running: {counts.running} | Aborted/Stopped: {counts.stopped}</div>
            </section>
          </div>
        </div>

        <section className="productionProgrammingCard liveSiteStatus">
          <header>LIVE SITE STATUS</header>
          <div className="channelTableWrap engineeringV2TableWrap">
            <table className="channelTable" aria-label="Engineering Site status">
              <thead><tr><th>SITE</th><th>TARGET IC</th><th>STATE</th><th>PROGRESS</th><th>RESULT</th><th>OPERATIONS (E/P/V/R)</th></tr></thead>
              <tbody>
                {selectedSites.map(site => (
                  <tr key={site.site_id} data-state={site.runtimeState}>
                    <td><b>{siteLabel(site.site_id)}</b></td>
                    <td><b>{targetDeviceLabel(targetDevice, site.target ?? "—")}</b><small>{site.interface ?? "—"}</small></td>
                    <td><span className="siteStatePill" data-state={site.runtimeState}>{site.runtimeState.toUpperCase()}</span>{site.error && <small className="errorText">{site.error}</small>}</td>
                    <td><div className="tableProgress"><div className="track"><i style={{ width: `${site.progress}%` }} /></div><b>{site.progress}%</b></div></td>
                    <td><b className="engineeringResult" data-result={resultLabel(site.runtimeState)}>{resultLabel(site.runtimeState)}</b></td>
                    <td><div className="rowActions engineeringV2Actions">
                      {operationOrder.map(operation => (
                        <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`SITE ${site.site_id} ${operation === "erase" ? "擦除" : operation === "program" ? "燒錄" : operation === "verify" ? "驗證" : "讀取"}`} title={`${operation} ${siteLabel(site.site_id)}`} disabled={executionLocked || !site.enabled || ((operation === "program" || operation === "verify") && ((!programmingImage && !syntheticMockImageAvailable) || imageTooLarge || unsupportedImage))} onClick={() => void runSingleSite(site.site_id, operation)}>{operationCodes[operation]}</button>
                      ))}
                      {site.jobId && site.outputFile && targetApiBase && <a className="rowDownload" aria-label={`Download SITE ${site.site_id} read file`} href={readDownloadUrl(targetApiBase, site.jobId, site.outputFile)}>↓</a>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="productionProgrammingCard recentEvents" aria-label="Engineering job log">
          <header>RECENT EVENTS</header>
          <div>
            {events.length === 0 && <p>—</p>}
            {events.map(entry => <p key={entry.id} data-level={entry.level}><time>{entry.time}</time><span>●</span>{entry.text}</p>)}
          </div>
        </section>
      </main>
    </section>
  );
}
