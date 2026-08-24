"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { beginBatchExecutionActivity } from "../../batch-execution-activity";
import { ICPickerField } from "../../devices/ic-picker-field";
import type { DeviceSearchResult } from "../../device-catalog-api";
import {
  engineeringTargetApiBase,
  getEngineeringTargets,
  getPPUStatus,
  type EngineeringTargetCatalog,
  type Operation,
  type SiteSnapshot,
} from "../../plasma-api";
import {
  cancelServerBatch,
  createServerBatch,
  getServerBatch,
  terminalServerBatchStates,
  type BatchSiteSnapshot,
  type ServerBatchSnapshot,
} from "../../server-batch-api";
import {
  batchTargetDeviceLabel,
  buildServerBatchOptions,
  manufacturingKpis,
  targetDeviceLabel,
  validateProgrammingDraft,
  type ProductionProgrammingJobDraft,
  type ProductionStopPolicy,
} from "../../production-programming-domain";
import { useWorkspaceSession } from "../../workspace-session";
import "./production-programming.css";

const operationOrder: Operation[] = ["erase", "program", "verify", "read"];
const operationCodes: Record<Operation, string> = {
  erase: "E",
  program: "P",
  verify: "V",
  read: "R",
};

const POLL_MS = 250;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

type EventEntry = { id: number; time: string; text: string; level?: "info" | "warn" | "error" };

function nowTime(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function orderedOperations(operations: Operation[]): Operation[] {
  return operationOrder.filter(operation => operations.includes(operation));
}

function batchSiteFor(batch: ServerBatchSnapshot | null, siteId: number): BatchSiteSnapshot | null {
  return batch?.sites.find(site => site.site_id === siteId) ?? null;
}

function siteState(site: SiteSnapshot, batchSite: BatchSiteSnapshot | null): string {
  if (batchSite) return batchSite.state;
  if (site.current_job_id || site.state === "running" || site.state === "queued") return "running";
  return site.enabled ? "idle" : "disabled";
}

function resultLabel(state: string): string {
  if (state === "success") return "PASS";
  if (state === "faulted") return "FAIL";
  if (state === "error") return "ERROR";
  if (state === "cancelled") return "CANCELLED";
  if (state === "stopped") return "STOPPED";
  return "—";
}

function cycleTimeLabel(batch: ServerBatchSnapshot | null, nowTick: number): string {
  if (!batch?.started_at) return "--";
  const start = Date.parse(batch.started_at);
  const finish = batch.finished_at ? Date.parse(batch.finished_at) : nowTick;
  if (!Number.isFinite(start) || !Number.isFinite(finish)) return "--";
  return `${Math.max(0, (finish - start) / 1000).toFixed(1)}s`;
}

export default function ProductionProgrammingPage() {
  const {
    hydrated,
    apiBase,
    ensureEngineeringSession,
    programmingImage,
    setProgrammingImage,
    pmodOperations,
    setPmodOperations,
  } = useWorkspaceSession();

  const [catalog, setCatalog] = useState<EngineeringTargetCatalog | null>(null);
  const [facilityId, setFacilityId] = useState("");
  const [ppuId, setPpuId] = useState("");
  const [sites, setSites] = useState<SiteSnapshot[]>([]);
  const [selectedSiteIds, setSelectedSiteIds] = useState<number[]>([]);
  const [targetDevice, setTargetDevice] = useState<DeviceSearchResult | null>(null);
  const [repeatCount, setRepeatCount] = useState("1");
  const [stopPolicy, setStopPolicy] = useState<ProductionStopPolicy>({ kind: "never" });
  const [activeBatch, setActiveBatch] = useState<ServerBatchSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const eventSequence = useRef(0);
  const releaseExecution = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const facility = catalog?.facilities.find(item => item.facility_id === facilityId) ?? null;
  const executionLocked = busy || Boolean(activeBatch && !terminalServerBatchStates.has(activeBatch.state));

  const appendEvent = useCallback((text: string, level: EventEntry["level"] = "info") => {
    setEvents(current => [{
      id: ++eventSequence.current,
      time: nowTime(),
      text,
      level,
    }, ...current].slice(0, 12));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;
    getEngineeringTargets(apiBase)
      .then(nextCatalog => {
        if (cancelled) return;
        setCatalog(nextCatalog);
        const firstFacility = nextCatalog.facilities[0];
        const firstPpu = firstFacility?.ppus[0];
        setFacilityId(current => current || firstFacility?.facility_id || "");
        setPpuId(current => current || firstPpu?.ppu_id || "");
        appendEvent(`Connected to ${nextCatalog.provider} topology.`);
      })
      .catch(loadError => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Failed to load topology.");
      });
    return () => { cancelled = true; };
  }, [apiBase, appendEvent, hydrated]);

  useEffect(() => {
    if (!facilityId || !ppuId) return;
    let cancelled = false;
    const targetBase = engineeringTargetApiBase(apiBase, facilityId, ppuId);
    getPPUStatus(targetBase)
      .then(status => {
        if (cancelled) return;
        setSites(status.sites);
        setSelectedSiteIds(status.sites.filter(site => site.enabled).map(site => site.site_id));
        appendEvent(`Loaded ${facilityId} / ${ppuId}.`);
      })
      .catch(loadError => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Failed to load PPU status.");
      });
    return () => { cancelled = true; };
  }, [apiBase, appendEvent, facilityId, ppuId]);

  useEffect(() => {
    if (!activeBatch || terminalServerBatchStates.has(activeBatch.state)) {
      releaseExecution.current?.();
      releaseExecution.current = null;
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const snapshot = await getServerBatch(apiBase, activeBatch.batch_id);
        if (cancelled) return;
        setActiveBatch(snapshot);
        if (terminalServerBatchStates.has(snapshot.state)) {
          setBusy(false);
          appendEvent(`Batch ${snapshot.batch_id.slice(-8)} completed: ${snapshot.state.toUpperCase()}.`, snapshot.state === "error" ? "error" : "info");
        }
      } catch (pollError) {
        if (!cancelled) {
          setBusy(false);
          setError(pollError instanceof Error ? pollError.message : "Batch polling failed.");
        }
      }
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeBatch, apiBase, appendEvent]);

  useEffect(() => () => {
    releaseExecution.current?.();
    releaseExecution.current = null;
  }, []);

  const draft = useMemo<ProductionProgrammingJobDraft>(() => ({
    facilityId,
    ppuId,
    siteIds: selectedSiteIds,
    targetDevice,
    programmingImage,
    operations: orderedOperations(pmodOperations),
    repeatCount: Number(repeatCount),
    stopPolicy,
  }), [facilityId, pmodOperations, ppuId, programmingImage, repeatCount, selectedSiteIds, stopPolicy, targetDevice]);

  const draftError = validateProgrammingDraft(draft);
  const imageTooLarge = Boolean(programmingImage && programmingImage.size > MAX_IMAGE_BYTES);
  const unsupportedImage = Boolean(programmingImage && !programmingImage.name.toLowerCase().endsWith(".bin"));
  const kpis = manufacturingKpis(activeBatch, selectedSiteIds.length);
  const runningSites = activeBatch?.site_counts.running ?? sites.filter(site => Boolean(site.current_job_id)).length;
  const liveTargetLabel = activeBatch?.target_device
    ? batchTargetDeviceLabel(activeBatch.target_device)
    : targetDeviceLabel(targetDevice);

  function chooseFacility(nextFacilityId: string) {
    if (executionLocked || !catalog) return;
    const nextFacility = catalog.facilities.find(item => item.facility_id === nextFacilityId);
    setError(null);
    setFacilityId(nextFacilityId);
    setPpuId(nextFacility?.ppus[0]?.ppu_id ?? "");
    setActiveBatch(null);
  }

  function choosePpu(nextPpuId: string) {
    if (executionLocked) return;
    setError(null);
    setPpuId(nextPpuId);
    setActiveBatch(null);
  }

  function toggleSite(siteId: number) {
    if (executionLocked) return;
    setSelectedSiteIds(current => current.includes(siteId)
      ? current.filter(id => id !== siteId)
      : [...current, siteId].sort((a, b) => a - b));
  }

  function toggleOperation(operation: Operation) {
    if (executionLocked) return;
    setPmodOperations(current => current.includes(operation)
      ? current.filter(item => item !== operation)
      : orderedOperations([...current, operation]));
  }

  async function submit(siteIds: number[], operations: Operation[]) {
    const nextDraft: ProductionProgrammingJobDraft = {
      ...draft,
      siteIds,
      operations: orderedOperations(operations),
    };
    const validation = validateProgrammingDraft(nextDraft);
    if (validation) {
      setError(validation);
      return;
    }
    if (imageTooLarge) {
      setError("Programming Image exceeds the current 4 MiB PMode limit.");
      return;
    }
    if (unsupportedImage) {
      setError("Current PMode normalizer supports binary Programming Image (.bin) only.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const requiresImage = nextDraft.operations.some(operation => operation === "program" || operation === "verify");
      const sessionId = requiresImage ? await ensureEngineeringSession(apiBase) : null;
      const snapshot = await createServerBatch(apiBase, buildServerBatchOptions(nextDraft, sessionId));
      releaseExecution.current?.();
      releaseExecution.current = beginBatchExecutionActivity();
      setActiveBatch(snapshot);
      appendEvent(
        `Start ${targetDeviceLabel(nextDraft.targetDevice)} · ${siteIds.map(siteLabel).join(", ")} · ${nextDraft.operations.map(operation => operationCodes[operation]).join("→")}.`,
      );
    } catch (submitError) {
      setBusy(false);
      setError(submitError instanceof Error ? submitError.message : "Batch submission failed.");
    }
  }

  async function abortBatch() {
    if (!activeBatch || terminalServerBatchStates.has(activeBatch.state)) return;
    setBusy(true);
    try {
      const snapshot = await cancelServerBatch(apiBase, activeBatch.batch_id);
      setActiveBatch(snapshot);
      appendEvent(`Abort requested for Batch ${activeBatch.batch_id.slice(-8)}.`, "warn");
    } catch (abortError) {
      setBusy(false);
      setError(abortError instanceof Error ? abortError.message : "Abort failed.");
    }
  }

  const stopPolicyValue = stopPolicy.kind === "never" ? "never" : String(stopPolicy.threshold);

  return (
    <main className="productionProgrammingV2">
      <header className="productionProgrammingHeader">
        <h1>SINGLE PPU PROGRAMMING</h1>
        <div><span className="onlineDot" /> Plasma Web REST <b>·</b> PMode</div>
      </header>

      <section className="productionProgrammingKpis" aria-label="Production programming KPIs">
        <article><small>SITES</small><b>{selectedSiteIds.length}</b></article>
        <article><small>TOTAL IC</small><b>{kpis.totalIc}</b></article>
        <article><small>RUNNING</small><b>{runningSites}</b></article>
        <article data-kpi="pass"><small>PASS</small><b>{kpis.pass}</b></article>
        <article data-kpi="fail"><small>FAIL</small><b>{kpis.fail}</b></article>
        <article data-kpi="yield"><small>YIELD</small><b>{kpis.yieldPercent.toFixed(1)}%</b></article>
        <article><small>CYCLE TIME</small><b>{cycleTimeLabel(activeBatch, nowTick)}</b></article>
      </section>

      <div className="productionProgrammingWorkflow">
        <section className="productionProgrammingCard targetingCard">
          <header>SYSTEM SETUP &amp; TARGETING</header>
          <div className="cardBody">
            <h2>SERVER TOPOLOGY</h2>
            <label className="workflowField">
              <span>Select Facility:</span>
              <select disabled={executionLocked || !catalog} value={facilityId} onChange={event => chooseFacility(event.target.value)}>
                {(catalog?.facilities ?? []).map(item => <option key={item.facility_id} value={item.facility_id}>{item.display_name}</option>)}
              </select>
            </label>
            <label className="workflowField">
              <span>Select PPU:</span>
              <select disabled={executionLocked || !facility} value={ppuId} onChange={event => choosePpu(event.target.value)}>
                {(facility?.ppus ?? []).map(item => <option key={item.ppu_id} value={item.ppu_id}>{item.display_name} - {item.site_count} Sites</option>)}
              </select>
            </label>

            <div className="targetSitesSection">
              <h2>TARGET SITES</h2>
              {sites.map(site => {
                const batchSite = batchSiteFor(activeBatch, site.site_id);
                const state = siteState(site, batchSite);
                return (
                  <label className="targetSiteRow" key={site.site_id}>
                    <input type="checkbox" checked={selectedSiteIds.includes(site.site_id)} disabled={executionLocked || !site.enabled} onChange={() => toggleSite(site.site_id)} />
                    <b>{siteLabel(site.site_id)}</b>
                    <span className="siteStatePill" data-state={state}>{state.toUpperCase()}</span>
                  </label>
                );
              })}
            </div>

            <div className="topologyFoot">ⓘ System Topology: {catalog?.facility_count ?? 0} Facilities | {catalog?.ppu_count ?? 0} PPUs | {catalog?.site_count ?? 0} Sites</div>
          </div>
        </section>

        <div className="productionProgrammingRight">
          <section className="productionProgrammingCard programmingJobCard">
            <header>PROGRAMMING JOB</header>
            <div className="cardBody programmingJobBody">
              <div className="jobRow">
                <strong>1. Target IC</strong>
                <ICPickerField apiBase={apiBase} value={targetDevice} onChange={setTargetDevice} disabled={executionLocked} placeholder="Search ICPN / IC identifier..." />
              </div>

              <div className="jobRow">
                <strong>2. Programming Image</strong>
                <div className="imageField">
                  <span title={programmingImage?.name}>{programmingImage?.name ?? "Select programming image (.bin)..."}</span>
                  <button type="button" disabled={executionLocked} onClick={() => fileInput.current?.click()}>Browse...</button>
                  <input
                    ref={fileInput}
                    type="file"
                    hidden
                    accept=".bin"
                    disabled={executionLocked}
                    onChange={event => setProgrammingImage(event.target.files?.[0] ?? null)}
                  />
                </div>
              </div>

              <div className="jobRow operationsRow">
                <strong>3. Operations</strong>
                <div className="operationChecks">
                  {operationOrder.map(operation => (
                    <label key={operation} title={operation}>
                      <input type="checkbox" disabled={executionLocked} checked={pmodOperations.includes(operation)} onChange={() => toggleOperation(operation)} />
                      <span>{operationCodes[operation]}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="jobRow batchPolicyRow">
                <strong>4. Batch Policy</strong>
                <label className="repeatField">Repeat: <input aria-label="Repeat" type="number" min="1" max="10000" disabled={executionLocked} value={repeatCount} onChange={event => setRepeatCount(event.target.value)} /></label>
                <label className="stopPolicyField">Stop Policy:
                  <select
                    aria-label="Stop Policy"
                    disabled={executionLocked || selectedSiteIds.length === 0}
                    value={stopPolicyValue}
                    onChange={event => setStopPolicy(event.target.value === "never" ? { kind: "never" } : { kind: "failed_sites", threshold: Number(event.target.value) })}
                  >
                    <option value="never">Never</option>
                    {selectedSiteIds.map((_, index) => <option key={index + 1} value={index + 1}>{index + 1} Fail</option>)}
                  </select>
                </label>
              </div>

              {(error || draftError || imageTooLarge || unsupportedImage) && (
                <div className="programmingGuard" role="alert">{error ?? (imageTooLarge
                  ? "Programming Image exceeds the current 4 MiB PMode limit."
                  : unsupportedImage
                    ? "Current PMode normalizer supports binary Programming Image (.bin) only."
                    : draftError)}</div>
              )}

              <div className="programmingActions">
                <button className="startProgramming" type="button" disabled={executionLocked || Boolean(draftError) || imageTooLarge || unsupportedImage} onClick={() => submit(selectedSiteIds, pmodOperations)}>▶ START PROGRAMMING</button>
                <button className="abortProgramming" type="button" disabled={!activeBatch || terminalServerBatchStates.has(activeBatch.state)} onClick={abortBatch}>■ ABORT</button>
              </div>
            </div>
          </section>

          <section className="productionProgrammingCard progressMonitor">
            <header>LIVE PROGRESS MONITOR</header>
            <div>Total selected: {selectedSiteIds.length} | Running: {runningSites} | Aborted/Stopped: {(activeBatch?.site_counts.cancelled ?? 0) + (activeBatch?.site_counts.stopped ?? 0)}</div>
          </section>
        </div>
      </div>

      <section className="productionProgrammingCard liveSiteStatus">
        <header>LIVE SITE STATUS</header>
        <div className="siteTable" role="table" aria-label="Live Site Status">
          <div className="siteTableHead" role="row">
            <span>SITE</span><span>TARGET IC</span><span>STATE</span><span>PROGRESS</span><span>RESULT</span><span>OPERATIONS (E/P/V/R)</span>
          </div>
          {sites.map(site => {
            const batchSite = batchSiteFor(activeBatch, site.site_id);
            const state = siteState(site, batchSite);
            const progress = Math.round(batchSite?.progress_percent ?? 0);
            return (
              <div className="siteTableRow" role="row" key={site.site_id} data-state={state}>
                <span>{siteLabel(site.site_id)}</span>
                <span className="targetIcCell">{liveTargetLabel}</span>
                <span><i className="siteStatePill" data-state={state}>{state.toUpperCase()}</i></span>
                <span className="progressCell"><i><b style={{ width: `${progress}%` }} /></i><em>{progress}%</em></span>
                <span className="resultCell" data-result={resultLabel(state)}>{resultLabel(state)}</span>
                <span className="siteOperationButtons">
                  {operationOrder.map(operation => (
                    <button
                      type="button"
                      key={operation}
                      title={`${operation} ${siteLabel(site.site_id)}`}
                      disabled={executionLocked || !site.enabled || !targetDevice || ((operation === "program" || operation === "verify") && (!programmingImage || unsupportedImage))}
                      onClick={() => submit([site.site_id], [operation])}
                    >{operationCodes[operation]}</button>
                  ))}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="productionProgrammingCard recentEvents">
        <header>RECENT EVENTS</header>
        <div>
          {events.length === 0 && <p>—</p>}
          {events.map(entry => <p key={entry.id} data-level={entry.level}><time>{entry.time}</time><span>●</span>{entry.text}</p>)}
        </div>
      </section>
    </main>
  );
}
