"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DeviceSearchResult } from "../device-catalog-api";
import { useI18n } from "../i18n";
import { BatchSummary } from "../operator-ui/batch-summary";
import { ProgrammingJobPanel } from "../operator-ui/programming-job-panel";
import { ProgrammingRunView } from "../operator-ui/programming-run-view";
import { PROGRAMMING_SOURCE_ACCEPT } from "../operator-ui/programming-source-selector";
import {
  describeBlocked,
  isImageOperation,
  loadManagedTopology,
  loadPlatformAvailability,
  loadProgrammingRoutes,
  MANAGED_JOB_POLICY,
  ManagedProgrammingBlocked,
  ManagedStartOutcomeUnknown,
  platformAvailability,
  routeOperations,
  routesAvailability,
  routeSites,
  runManagedProgramming,
  runProgressPercent,
  runStageLabel,
  runVerdict,
  siteCapability,
  type LockedInput,
  type ManagedAvailability,
  type ManagedTopology,
  type ProgrammingPlan,
  type ProgrammingRun,
  type ProgrammingSource,
  type RoutesState,
} from "../programming/managed-programming";
import { acknowledgeProgrammingRun } from "./bundle-programming-api";
import EngineeringLogPanel, {
  engineeringLogCategoryLabel,
  type EngineeringLogCategory,
  type EngineeringLogEntry,
} from "./engineering-log-panel";
import "./programming-workspace-base.css";
import "./programming-workspace-v2.css";

// EMode Single PPU Programming on the formal backend.
// Console -> BFF -> Manager Registry / Fleet / Programming Routes -> Manager
// programming plan + run. This component imports no PPU Gateway client: the
// Browser cannot submit, retry or cancel a Job on a PPU directly.

const TOPOLOGY_POLL_MS = 3000;
const PLATFORM_POLL_MS = 5000;
const MAX_LOG_ENTRIES = 1000;
const MAX_SOURCE_BYTES: Record<ProgrammingSource, number> = {
  image: 1024 * 1024,
  bundle: 1024 * 1024 + 256 * 1024,
};
// Catalog Level is not a programming gate; the Programming Route decides.
const PICKER_LEVELS: Array<1 | 2 | 3> = [1, 2, 3];
const OPERATION_LABELS: Record<string, { code: string; label: string }> = {
  flash_cycle: { code: "F", label: "Flash Cycle" },
  program: { code: "P", label: "Program" },
  verify: { code: "V", label: "Verify" },
  erase: { code: "E", label: "Erase" },
  read: { code: "R", label: "Read" },
};

type ConnectionState = "connecting" | "online" | "offline";
type Phase = "idle" | "locking" | "planning" | "starting" | "running";
type Readiness = { ready: boolean; label: string; reason: string };
type RunContext = { alias: string; siteId: number; startedAt: number; finishedAt: number | null };

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function formatElapsed(milliseconds: number | null): string {
  if (milliseconds === null || milliseconds < 0) return "00:00:00";
  const total = Math.floor(milliseconds / 1000);
  return [Math.floor(total / 3600), Math.floor((total % 3600) / 60), total % 60]
    .map(value => String(value).padStart(2, "0")).join(":");
}

function notReady(label: string, reason: string): Readiness {
  return { ready: false, label, reason };
}

function fromAvailability(availability: ManagedAvailability): Readiness | null {
  return availability.ready ? null : notReady(availability.label, availability.reason);
}

export default function ManagedProgrammingWorkspace() {
  const { locale } = useI18n();

  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [topology, setTopology] = useState<ManagedTopology | null>(null);
  const [topologyError, setTopologyError] = useState<string | null>(null);
  const [selectedAlias, setSelectedAlias] = useState<string | null>(null);
  const [routesByAlias, setRoutesByAlias] = useState<Record<string, RoutesState>>({});
  const [platform, setPlatform] = useState<{ alias: string; availability: ManagedAvailability } | null>(null);

  const [targetDevice, setTargetDevice] = useState<DeviceSearchResult | null>(null);
  const [source, setSource] = useState<ProgrammingSource>("image");
  const [file, setFile] = useState<File | null>(null);
  const [chosenSiteId, setChosenSiteId] = useState<number | null>(null);
  const [chosenOperation, setChosenOperation] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [locked, setLocked] = useState<LockedInput | null>(null);
  const [plan, setPlan] = useState<ProgrammingPlan | null>(null);
  const [run, setRun] = useState<ProgrammingRun | null>(null);
  const [runContext, setRunContext] = useState<RunContext | null>(null);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const [startUnknown, setStartUnknown] = useState<string | null>(null);
  const [unresolved, setUnresolved] = useState<ProgrammingRun | null>(null);
  const [acknowledging, setAcknowledging] = useState(false);
  const [statusNote, setStatusNote] = useState<string | null>(null);

  const [logs, setLogs] = useState<EngineeringLogEntry[]>([]);
  const [clock, setClock] = useState(() => Date.now());
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [jobCollapsed, setJobCollapsed] = useState(false);

  const startLock = useRef(false);
  const logSequence = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const appendLog = useCallback((message: string, error = false, category: EngineeringLogCategory = "SYS") => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs(current => [
      { id: ++logSequence.current, text: `${time}  [${engineeringLogCategoryLabel(category)}] ${message}`, error, category },
      ...current,
    ].slice(0, MAX_LOG_ENTRIES));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Registry + Fleet: the only topology source.
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let announced = false;
    async function refresh() {
      try {
        const next = await loadManagedTopology();
        if (stopped) return;
        setTopology(next);
        setTopologyError(null);
        setConnection("online");
        if (!announced) {
          announced = true;
          const sites = next.ppus.reduce((total, ppu) => total + ppu.siteCount, 0);
          appendLog(`[MANAGER] Registry · ${next.facilities.length} Facilities · ${next.ppus.length} PPUs · ${sites} Sites`, false, "NET");
        }
        setSelectedAlias(current => (
          current && next.ppus.some(ppu => ppu.alias === current) ? current : next.ppus[0]?.alias ?? null
        ));
      } catch (reason) {
        if (stopped) return;
        const message = reason instanceof Error ? reason.message : "Manager Registry unavailable";
        setTopologyError(message);
        setConnection("offline");
        if (announced || logSequence.current === 0) appendLog(`[MANAGER] Registry unavailable · ${message}`, true, "NET");
        announced = false;
      } finally {
        if (!stopped) timer = setTimeout(refresh, TOPOLOGY_POLL_MS);
      }
    }
    void refresh();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [appendLog]);

  // Programming Routes and Platform admission of the selected PPU (reads only).
  useEffect(() => {
    if (!selectedAlias) return;
    const alias = selectedAlias;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    void loadProgrammingRoutes(alias).then(state => {
      if (!stopped) setRoutesByAlias(current => ({ ...current, [alias]: state }));
    });
    async function refresh() {
      const availability = await loadPlatformAvailability(alias);
      if (stopped) return;
      setPlatform({ alias, availability });
      timer = setTimeout(refresh, PLATFORM_POLL_MS);
    }
    void refresh();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [selectedAlias]);

  const ppu = topology?.ppus.find(item => item.alias === selectedAlias) ?? null;
  const facility = topology?.facilities.find(item => item.facilityId === ppu?.facilityId) ?? null;
  const routesState = selectedAlias ? routesByAlias[selectedAlias] ?? null : null;
  const routes = routesState?.routes ?? null;
  const platformState = platform && platform.alias === selectedAlias
    ? platform.availability
    : platformAvailability(null, null);
  const icpn = targetDevice?.icpn ?? targetDevice?.identifier ?? null;
  const active = phase !== "idle";

  const capabilities = useMemo(
    () => new Map((ppu?.sites ?? []).map(site => [site.site_id, siteCapability(site, routes, icpn)] as const)),
    [ppu, routes, icpn],
  );
  // A Site stays selected only while it is programmable for the selected IC.
  const siteId = chosenSiteId != null && capabilities.get(chosenSiteId)?.programmable ? chosenSiteId : null;
  const operationOptions = useMemo(() => routeOperations(routes, icpn, siteId), [routes, icpn, siteId]);
  const operation = chosenOperation != null && (operationOptions as string[]).includes(chosenOperation)
    ? chosenOperation
    : operationOptions.length === 1 ? operationOptions[0] : null;

  const readiness: Readiness = (() => {
    if (active) return notReady("RUNNING", "A programming run is in progress; this selection is locked.");
    if (connection !== "online" || !topology) {
      return notReady("MANAGER OFFLINE", topologyError ?? "Connecting to the Manager Registry.");
    }
    if (!ppu) return notReady("NO PPU", "No commissioned PPU is registered. Register one in PPU → Registration.");
    const ppuBlock = fromAvailability(ppu.availability) ?? fromAvailability(platformState)
      ?? fromAvailability(routesAvailability(routesState));
    if (ppuBlock) return ppuBlock;
    if (unresolved && unresolved.ppu_alias === ppu.alias && !unresolved.acknowledged) {
      return notReady("OUTCOME UNKNOWN",
        "The previous run on this PPU ended OUTCOME UNKNOWN. Reconcile the PPU and acknowledge it; nothing is resubmitted.");
    }
    if (!icpn) return notReady("NO TARGET", "Select a Target IC.");
    if (!routeSites(routes, icpn).length) {
      return notReady("NO ROUTE", `No Programming Route declares ${icpn}; this IC cannot be programmed on a managed PPU yet.`);
    }
    if (siteId == null) return notReady("NO SITE", `Select one Site qualified for ${icpn}.`);
    if (!operation) return notReady("NO OP", "Select one Operation.");
    if (!isImageOperation(operation)) {
      return notReady("OPERATION UNAVAILABLE", `${operation} needs an explicit address range, which this page does not collect.`);
    }
    if (!file) {
      return source === "bundle"
        ? notReady("BUNDLE REQUIRED", "Select your canonical Bundle v3 (.zip).")
        : notReady("IMAGE REQUIRED", "Select a Programming Image (.bin).");
    }
    if (file.size <= 0 || file.size > MAX_SOURCE_BYTES[source]) {
      return notReady("FILE INVALID", `The selected file must be 1 to ${MAX_SOURCE_BYTES[source]} bytes.`);
    }
    return { ready: true, label: "BATCH READY", reason: "" };
  })();

  function clearRunState() {
    setLocked(null);
    setPlan(null);
    setRun(null);
    setRunContext(null);
    setBlockedMessage(null);
    setStartUnknown(null);
    setStatusNote(null);
  }

  function selectAlias(alias: string | null) {
    if (active || alias === selectedAlias) return;
    setSelectedAlias(alias);
    setChosenSiteId(null);
    clearRunState();
    if (alias) appendLog(`[TARGET] SELECT · PPU ${alias}`, false, "USR");
  }

  function selectFacility(facilityId: string) {
    const next = topology?.facilities.find(item => item.facilityId === facilityId);
    selectAlias(next?.ppus[0]?.alias ?? null);
  }

  function selectTargetDevice(device: DeviceSearchResult | null) {
    if (active) return;
    setTargetDevice(device);
    clearRunState();
    if (device) appendLog(`[TARGET IC] SELECT · ${device.vendor} / ${device.icpn ?? device.identifier}`, false, "USR");
  }

  // Switching the Programming Source only clears local state. It never plans,
  // deploys, flashes or creates a Job.
  function changeSource(next: ProgrammingSource) {
    if (active || next === source) return;
    setSource(next);
    setFile(null);
    clearRunState();
    appendLog(`[SOURCE] ${next.toUpperCase()} · previous file and plan cleared`, false, "USR");
  }

  function selectFile(next: File | null) {
    if (active) return;
    setFile(next);
    clearRunState();
    appendLog(next ? `[IMG] SELECT ${source.toUpperCase()} · ${next.name} · ${next.size} B` : "[IMG] CLEAR", false, "USR");
  }

  function toggleSite(id: number) {
    if (active) return;
    const next = siteId === id ? null : id;
    setChosenSiteId(next);
    clearRunState();
    appendLog(`[SITE] SELECTION · ${next == null ? "none" : siteLabel(next)}`, false, "USR");
  }

  async function start() {
    // Double-click protection: the lock is taken synchronously, before any await.
    if (startLock.current || !readiness.ready || !ppu || siteId == null || !icpn || !file
      || !isImageOperation(operation)) return;
    startLock.current = true;
    const request = { alias: ppu.alias, siteId, icpn, operation, source, file };
    const context: RunContext = { alias: ppu.alias, siteId, startedAt: Date.now(), finishedAt: null };
    const abort = new AbortController();
    abortRef.current = abort;
    clearRunState();
    setRunContext(context);
    setPhase("locking");
    appendLog(`[START] ${operation.toUpperCase()} · PPU ${ppu.alias} (${ppu.ppuId ?? "—"}) · ${siteLabel(siteId)} · ${icpn} · ${source.toUpperCase()} ${file.name}`, false, "USR");
    try {
      const final = await runManagedProgramming(request, {
        onLocked: input => {
          setLocked(input);
          setPhase("planning");
          appendLog(`[LOCK] ${input.source.toUpperCase()} · ${input.name} · ${input.size} B · SHA256 ${input.sha256}`, false, "DAT");
        },
        onPlan: next => {
          setPlan(next);
          setPhase("starting");
          appendLog(`[PLAN] ${next.plan_id} · ${next.activation_required ? "B1/B2/B3 activation" : "Resource Reuse"} · Binding ${next.job_binding_sha256}`);
        },
        onRun: next => {
          setRun(next);
          setPhase("running");
          setStatusNote(null);
        },
        onPollError: message => setStatusNote(message),
      }, abort.signal);
      const { verdict, reason } = runVerdict(final);
      appendLog(`[RESULT] ${verdict}${reason ? ` · ${reason}` : ""} · Run ${final.run_id} · Job ${final.receipt?.job_id ?? final.job?.job_id ?? "—"}`,
        verdict !== "PASS", "PPU");
      if (final.outcome === "OUTCOME_UNKNOWN") setUnresolved(final);
    } catch (reason) {
      if (reason instanceof ManagedProgrammingBlocked) {
        const message = describeBlocked(reason);
        setBlockedMessage(message);
        appendLog(`[BLOCKED] ${reason.stage.toUpperCase()} · ${message} · no Job was submitted`, true);
      } else if (reason instanceof ManagedStartOutcomeUnknown) {
        setStartUnknown(reason.message);
        appendLog(`[OUTCOME UNKNOWN] ${reason.message}`, true);
      } else {
        const message = reason instanceof Error ? reason.message : "Programming failed";
        setBlockedMessage(message);
        appendLog(`[ERROR] ${message}`, true);
      }
    } finally {
      setRunContext(current => current ? { ...current, finishedAt: Date.now() } : current);
      setPhase("idle");
      startLock.current = false;
    }
  }

  async function acknowledge() {
    if (!unresolved || acknowledging) return;
    setAcknowledging(true);
    try {
      const next = await acknowledgeProgrammingRun(unresolved.ppu_alias, unresolved.run_id);
      setUnresolved(next.acknowledged ? null : next);
      setRun(current => current?.run_id === next.run_id ? next : current);
      appendLog(`[ACK] OUTCOME UNKNOWN reconciled · Run ${next.run_id}`, false, "USR");
    } catch (reason) {
      setStatusNote(reason instanceof Error ? reason.message : "Acknowledge failed");
    } finally {
      setAcknowledging(false);
    }
  }

  const verdict = run ? runVerdict(run).verdict : null;
  const pass = verdict === "PASS" ? 1 : 0;
  const fail = verdict === "FAIL" ? 1 : 0;
  const elapsed = runContext ? (runContext.finishedAt ?? clock) - runContext.startedAt : null;
  const kpis = [
    { key: "sites", label: "SITES", value: siteId == null && !runContext ? 0 : 1 },
    { key: "total-ic", label: "TOTAL IC", value: siteId == null && !runContext ? 0 : 1 },
    { key: "processed-ic", label: "PROCESSED IC", value: pass + fail },
    { key: "pass", label: "PASS", value: pass, tone: "pass" as const },
    { key: "fail", label: "FAIL", value: fail, tone: "fail" as const },
    { key: "yield", label: "YIELD", value: pass + fail > 0 ? `${((pass / (pass + fail)) * 100).toFixed(1)}%` : "—", tone: "info" as const },
    { key: "batch-time", label: "BATCH TIME", value: formatElapsed(elapsed) },
  ];
  const sourceLabel = source === "bundle" ? "Bundle" : "Image";
  const imageName = file?.name
    ?? (source === "bundle" ? "Select canonical Bundle v3 (.zip)..." : "Select programming image (.bin)...");
  const imageHint = locked
    ? `Locked ${locked.source} · ${locked.size} B · SHA256 ${locked.sha256}`
    : source === "bundle"
      ? "Your own canonical Bundle v3. The Manager verifies it against the qualified Programming Route."
      : "Binary Programming Image (.bin). The Manager builds the canonical Bundle v3.";
  const policyNote = locale === "zh-TW"
    ? `正式 Flash Job：attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}。Repeat／Retry／Stop Policy 與 ABORT 尚無正式執行契約，已停用。`
    : `Formal Flash Job: attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}. Repeat / Retry / Stop Policy and ABORT have no formal execution contract and are disabled.`;
  const phaseLabel = phase === "locking" ? "LOCKING" : phase === "planning" ? "PLANNING"
    : phase === "starting" ? "STARTING" : run && run.outcome == null ? runStageLabel(run) : readiness.label;

  return (
    <section className="engineeringProgramming engineeringProgrammingV2" data-programming-backend="manager">
      <main className="productionProgrammingV2">
        <header className="productionProgrammingHeader engineeringProgrammingV2Header">
          <h1>SINGLE PPU PROGRAMMING</h1>
          <div className={`engineeringGateway ${connection}`} role="status" aria-label="Programming Backend">
            <span className="onlineDot" />
            <output data-testid="managed-backend">
              Manager Registry · {connection === "online" ? "ONLINE" : connection === "offline" ? "OFFLINE" : "CONNECTING"}
              {ppu ? ` · PPU ${ppu.alias}` : ""}
            </output>
            <b>EMode</b>
          </div>
        </header>

        <BatchSummary
          items={kpis}
          ariaLabel="Engineering Batch Summary"
          title="BATCH SUMMARY"
          meta={`${runContext ? "Current Run" : "Run Preview"} · ${kpis[0].value} Sites · ${kpis[1].value} ICs`}
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
                  value={facility?.facilityId ?? ""}
                  disabled={!topology || active}
                  onChange={event => selectFacility(event.target.value)}
                >
                  {(topology?.facilities ?? []).map(item => <option key={item.facilityId} value={item.facilityId}>{item.displayName}</option>)}
                </select>
              </label>
              <label className="workflowField">
                <span>Select PPU:</span>
                <select
                  aria-label="Engineering PPU"
                  value={ppu?.alias ?? ""}
                  disabled={!facility || active}
                  onChange={event => selectAlias(event.target.value)}
                >
                  {(facility?.ppus ?? []).map(item => (
                    <option key={item.alias} value={item.alias}>
                      {item.alias} — {item.ppuId ?? "PPU ID unknown"} — {item.siteCount} Sites — {item.availability.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="topologyFoot" aria-label="Selected Engineering PPU">
                <b>{facility?.displayName ?? "No Facility"} / {ppu?.displayName ?? "No PPU"}</b>
                {' · '}Manager Alias: {ppu?.alias ?? "—"}{' · '}PPU ID: {ppu?.ppuId ?? "—"}{' · '}{ppu?.siteCount ?? 0} Sites
                {' · '}{ppu ? (ppu.online ? "PPU ONLINE" : "PPU OFFLINE") : "—"}
                {' · '}System Topology: {topology?.facilities.length ?? 0} Facilities | {topology?.ppus.length ?? 0} PPUs
                {' | '}{(topology?.ppus ?? []).reduce((total, item) => total + item.siteCount, 0)} Sites
              </div>
            </div>
          </section>

          <div className="productionProgrammingRight">
            <ProgrammingJobPanel
              mode="engineering"
              title="PROGRAMMING JOB"
              collapsed={jobCollapsed}
              onToggleCollapsed={() => setJobCollapsed(current => !current)}
              expandLabel={locale === "zh-TW" ? "展開" : "Show"}
              collapseLabel={locale === "zh-TW" ? "收合" : "Hide"}
              targetDevice={targetDevice}
              onTargetChange={selectTargetDevice}
              targetDisabled={active}
              targetPlaceholder="Search ICPN / IC identifier..."
              targetLabel="Target IC"
              targetLevels={PICKER_LEVELS}
              imageLabel="Programming Source"
              source={{ value: source, disabled: active, onChange: changeSource }}
              image={{
                name: imageName,
                title: imageName,
                source: file ? `user_${source}` : "none",
                hint: imageHint,
                browseLabel: "Browse...",
                browseDisabled: active,
                inputDisabled: active,
                inputAriaLabel: `Engineering Programming ${sourceLabel} file`,
                accept: PROGRAMMING_SOURCE_ACCEPT[source],
                onFileChange: next => selectFile(next),
              }}
              operationsLabel="Operations"
              operations={operationOptions.map(item => ({
                key: item,
                code: OPERATION_LABELS[item]?.code ?? "?",
                label: OPERATION_LABELS[item]?.label ?? item,
                checked: operation === item,
                // Only what the Route declares is listed; range Operations need inputs this page lacks.
                disabled: active || !isImageOperation(item),
                ariaLabel: `Engineering operation ${item}`,
                onChange: () => { setChosenOperation(operation === item ? null : item); clearRunState(); },
              }))}
              policyLabel="Batch Policy"
              policy={{
                repeatLabel: "Repeat",
                repeatValue: String(MANAGED_JOB_POLICY.attempts),
                repeatDisabled: true,
                repeatAriaLabel: "Repeat Count",
                onRepeatChange: () => {},
                retryLabel: "Retry",
                retryValue: "0",
                retryDisabled: true,
                retryAriaLabel: "Site Retry Limit",
                onRetryChange: () => {},
                stopLabel: "Stop Policy",
                stopValue: "unavailable",
                stopDisabled: true,
                stopAriaLabel: "Engineering Stop Policy",
                stopOptions: [{ value: "unavailable", label: "Unavailable" }],
                onStopChange: () => {},
                note: policyNote,
              }}
              startLabel="START PROGRAMMING"
              startDisabled={!readiness.ready}
              onStart={start}
              statusLabel="BATCH STATUS"
              statusValue={phaseLabel}
              statusClassName={`readiness-${readiness.ready ? "batch-ready" : active ? "running" : "programming-unavailable"}`}
              abortLabel="ABORT"
              abortDisabled
              onAbort={() => {}}
            />

            {!readiness.ready && !active && (
              <div className="engineeringBoundaryNote warning" role="status" data-testid="managed-readiness">
                <b>{readiness.label}</b><span>{readiness.reason}</span>
              </div>
            )}
            {blockedMessage && (
              <div className="warning engineeringOperationWarning" role="alert" data-testid="managed-blocked">
                <span>Not started — no Job was submitted. {blockedMessage}</span>
              </div>
            )}
            {startUnknown && (
              <div className="warning engineeringOperationWarning" role="alert" data-testid="managed-start-unknown">
                <span>OUTCOME UNKNOWN — {startUnknown} Check the PPU before programming again.</span>
              </div>
            )}
            {statusNote && <div className="warning engineeringOperationWarning" role="status">{statusNote}</div>}
          </div>
        </div>

        {plan && (
          <section className="productionProgrammingCard" aria-label="Programming plan" data-testid="managed-plan">
            <header><span>PROGRAMMING PLAN</span><small>Built and verified by the Manager for this Start</small></header>
            <dl className="cardBody programmingRunView">
              <dt>PPU / Site</dt><dd>{plan.ppu_alias} / Site {plan.site_id}</dd>
              <dt>Route</dt><dd>{plan.route.route_id} ({plan.route.provider} → {plan.route.profile})</dd>
              <dt>Source</dt><dd data-testid="plan-source">{plan.source}</dd>
              <dt>Operation</dt><dd data-testid="plan-operation">{plan.operation}</dd>
              <dt>Range</dt><dd>0x{plan.job_binding.range.address.toString(16)} · {plan.job_binding.range.length} B</dd>
              <dt>Resource SHA256</dt><dd data-testid="plan-resource-sha"><code>{plan.resource.resource_set_sha256}</code></dd>
              <dt>Job Binding SHA256</dt><dd data-testid="plan-binding-sha"><code>{plan.job_binding_sha256}</code></dd>
              <dt>Resources</dt>
              <dd data-testid="plan-activation">
                {plan.activation_required
                  ? "Activation: B1 upload → B2 admit → B3 activate (no FPGA load)"
                  : "Resource Reuse: the PPU verified identical Programming Resources (no B1/B2/B3, no FPGA load)"}
              </dd>
            </dl>
          </section>
        )}

        {run && <ProgrammingRunView run={run} ariaLabel="Programming run" />}
        {unresolved && !unresolved.acknowledged && (
          <div className="warning engineeringOperationWarning" role="alert" data-testid="managed-unresolved">
            <span>
              Run {unresolved.run_id} on PPU {unresolved.ppu_alias} ended OUTCOME UNKNOWN. Nothing was resubmitted.
              Reconcile the PPU through the normal recovery procedure, then acknowledge.
            </span>
            <button type="button" disabled={acknowledging} onClick={() => void acknowledge()}>Acknowledge reconciliation</button>
          </div>
        )}

        <section className="productionProgrammingCard liveSiteStatus overviewCard" aria-label="Engineering Site status">
          <header>
            <span>LIVE SITE STATUS</span>
            <small>{ppu?.displayName ?? "Selected PPU"} · {ppu?.sites.length ?? 0} Sites · Selected {siteId == null ? 0 : 1} · Manager Fleet polling {TOPOLOGY_POLL_MS / 1000} s</small>
          </header>
          <div className="channelTableWrap engineeringV2TableWrap" role="region" aria-label="Engineering Site selection">
            <table className="channelTable">
              <thead>
                <tr><th>SELECT</th><th>SITE</th><th>TARGET IC</th><th>STATE</th><th>PROGRESS</th><th>RESULT</th><th>PROGRAMMING CAPABILITY</th></tr>
              </thead>
              <tbody className="targetSitesSection">
                {(ppu?.sites ?? []).map(site => {
                  const capability = capabilities.get(site.site_id);
                  const selected = siteId === site.site_id;
                  const ownsRun = run != null && runContext?.alias === ppu?.alias && runContext?.siteId === site.site_id;
                  const progress = ownsRun ? runProgressPercent(run) : null;
                  const rowVerdict = ownsRun ? runVerdict(run).verdict : null;
                  const state = ownsRun && run.outcome == null ? runStageLabel(run)
                    : site.enabled ? site.state.toUpperCase() : "DISABLED";
                  return (
                    <tr key={site.site_id} data-site-selected={selected ? "true" : "false"} data-site-enabled={site.enabled ? "true" : "false"}
                      data-site-programmable={capability?.programmable ? "true" : "false"}>
                      <td className="engineeringBatchSelectCell">
                        <input
                          type="checkbox"
                          aria-label={`Select SITE ${site.site_id} for programming`}
                          checked={selected}
                          disabled={active || !capability?.programmable}
                          onChange={() => toggleSite(site.site_id)}
                        />
                      </td>
                      <td><b>{siteLabel(site.site_id)}</b></td>
                      <td><b>{icpn ?? site.target ?? "—"}</b><small>{site.interface ?? "—"}</small></td>
                      <td><span className="state">{state}</span></td>
                      <td>{progress == null
                        ? <b>—</b>
                        : <div className="tableProgress"><div className="track"><i style={{ width: `${progress}%` }} /></div><b>{Math.round(progress)}%</b></div>}</td>
                      <td><b className="engineeringResult" data-result={rowVerdict ?? "—"}>{rowVerdict == null || rowVerdict === "RUNNING" ? "—" : rowVerdict.replace("_", " ")}</b></td>
                      <td><b>{capability?.label ?? "—"}</b>{capability?.reason && <small>{capability.reason}</small>}</td>
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
