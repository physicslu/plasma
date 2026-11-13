"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DeviceSearchResult } from "../device-catalog-api";
import { useI18n } from "../i18n";
import { BatchSummary } from "../operator-ui/batch-summary";
import { OperatorPanelHeader } from "../operator-ui/operator-panel";
import { ProgrammingJobPanel } from "../operator-ui/programming-job-panel";
import { PROGRAMMING_SOURCE_ACCEPT } from "../operator-ui/programming-source-selector";
import { programmingRunLogLines, safeOffLogLabel } from "../programming/programming-run-log";
import {
  batchSiteVerdict,
  batchVerdict,
  runOfUnit,
  describeBlocked,
  loadManagedTopology,
  loadPlatformAvailability,
  loadProgrammingRoutes,
  MANAGED_JOB_POLICY,
  decideStartReconciliation,
  ManagedProgrammingBlocked,
  ManagedStartOutcomeUnknown,
  platformAvailability,
  routeDeclaring,
  routesAvailability,
  routeSequenceOperations,
  routeSites,
  runManagedBatch,
  runManagedRead,
  runProgressPercent,
  runStageLabel,
  runVerdict,
  siteCapability,
  type LockedInput,
  type ManagedAvailability,
  type ManagedBatchRequest,
  type ManagedTopology,
  type ProgrammingBatch,
  type ProgrammingRun,
  type ProgrammingSource,
  type RoutesState,
  type StartIdentity,
} from "../programming/managed-programming";
import {
  acknowledgeProgrammingRun,
  getStartReconciliation,
  voidStart,
  MAX_RETRY_LIMIT,
  normalizeOperations,
  operationsTakeImage,
  SEQUENCE_OPERATIONS,
  stopProgrammingBatch,
  type SequenceOperation,
  type StopPolicy,
} from "./bundle-programming-api";
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
// Three basic Operations, freely combined; the order is always E -> P -> V and
// the whole selection runs as ONE programming Job. Read is not one of them.
const OPERATION_LABELS: Record<SequenceOperation, { code: string; label: string }> = {
  erase: { code: "E", label: "Erase" },
  program: { code: "P", label: "Program" },
  verify: { code: "V", label: "Verify" },
};
const ALL_OPERATIONS: Record<SequenceOperation, boolean> = { erase: true, program: true, verify: true };

type ConnectionState = "connecting" | "online" | "offline";
type Phase = "idle" | "locking" | "planning" | "starting" | "running";
type ReadPhase = "idle" | "choosing" | "planning" | "running" | "saving";
// One line per Site: the evidence (Job, SHA256, SAFE_OFF) lives in the Log.
type SiteRead = {
  status: "PASS" | "FAIL" | "BLOCKED" | "OUTCOME UNKNOWN" | "SAVE FAILED";
  detail: string;
  /** Verified bytes offered as a Browser download (no Save File Picker, or the write failed). */
  download: { url: string; filename: string } | null;
};
type SaveFilePicker = (options?: {
  suggestedName?: string;
  types?: Array<{ description?: string; accept: Record<string, string[]> }>;
}) => Promise<FileSystemFileHandle>;

/** The native Save File Picker; null where the Browser has none (Firefox, Safari, insecure origin). */
function saveFilePicker(): SaveFilePicker | null {
  const picker = (window as unknown as { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker;
  return typeof picker === "function" ? picker.bind(window) : null;
}
type Readiness = { ready: boolean; label: string; reason: string };
type RunContext = { alias: string; siteIds: number[]; startedAt: number; finishedAt: number | null };

// A Start request whose answer was lost (timeout, 5xx, dropped connection): the
// Manager may or may not have submitted a Job. The Manager stays the authority
// (one-shot plan, journal, one active run per PPU, OUTCOME UNKNOWN latch); this
// hold only keeps THIS Console from sending another write to the PPU until the
// operator reconciles it. It is stored so a reload cannot drop it.
const START_HOLD_KEY = "plasma.emode.start-outcome-unknown.v1";
// The hold is UX recovery only: it remembers WHICH Manager start to ask about.
// Whether that start ran, and how it ended, is the Manager's journal alone.
type StartHold = {
  alias: string;
  /** Every Site the lost Start was for. A READ holds exactly one. */
  siteIds: number[];
  /** Written by releases before PR-C, when a Batch was one Site. */
  siteId?: number;
  kind: "READ" | "PROGRAMMING"; detail: string; at: string;
  /** Manager-issued start ID (run plan ID / Batch start ID); null: not reconcilable. */
  startId: string | null;
  jobBindingSha256: string | null;
};

/** A hold stored before this release holds one Site; it still blocks. */
function holdSites(hold: StartHold): number[] {
  if (Array.isArray(hold.siteIds) && hold.siteIds.length) return hold.siteIds;
  return hold.siteId == null ? [] : [hold.siteId];
}
type HoldStep = { startId: string; action: "ACKNOWLEDGE_RUN" | "VOID" };
let heldStarts: Record<string, StartHold> = {};

function readStartHolds(): Record<string, StartHold> {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(START_HOLD_KEY) ?? "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      heldStarts = { ...heldStarts, ...(parsed as Record<string, StartHold>) };
    }
  } catch {
    // Storage unavailable: the hold still lives for this page.
  }
  return heldStarts;
}

function writeStartHolds(next: Record<string, StartHold>) {
  heldStarts = next;
  try {
    if (Object.keys(next).length) window.localStorage.setItem(START_HOLD_KEY, JSON.stringify(next));
    else window.localStorage.removeItem(START_HOLD_KEY);
  } catch {
    // Storage unavailable: the hold still lives for this page.
  }
}

function siteLabel(siteId: number): string {
  return `SITE-${String(siteId).padStart(2, "0")}`;
}

function formatElapsed(milliseconds: number | null): string {
  if (milliseconds === null || milliseconds < 0) return "00:00:00";
  const total = Math.floor(milliseconds / 1000);
  return [Math.floor(total / 3600), Math.floor((total % 3600) / 60), total % 60]
    .map(value => String(value).padStart(2, "0")).join(":");
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB (${bytes} B)`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB (${bytes} B)`;
}

/** Format shown next to the picked file; only what the Browser exposes (never a local path). */
function fileFormat(file: File, source: ProgrammingSource): string {
  const extension = /\.([A-Za-z0-9]{1,8})$/.exec(file.name)?.[1]?.toLowerCase();
  if (source === "bundle") return extension === "zip" ? "Canonical Bundle v3 (.zip)" : `Bundle (.${extension ?? "?"})`;
  return extension === "bin" ? "Raw binary (.bin)" : `Binary image (.${extension ?? "no extension"})`;
}

function hex(value: number): string {
  return `0x${value.toString(16).toUpperCase().padStart(8, "0")}`;
}

/** Wall-clock time of a user action (Start); never read while rendering. */
function wallClock(): number {
  return Date.now();
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
  // EMode covers many Sites of ONE PPU: the Manager schedules them
  // sequentially as one Batch and judges each Site on its own.
  const [chosenSiteIds, setChosenSiteIds] = useState<number[]>([]);
  const [checkedOperations, setCheckedOperations] = useState(ALL_OPERATIONS);

  const [phase, setPhase] = useState<Phase>("idle");
  const [locked, setLocked] = useState<LockedInput | null>(null);
  const [run, setRun] = useState<ProgrammingRun | null>(null);
  // Batch Policy: Manager-owned Retry and Stop Policy. Repeat is fixed at 1.
  const [retryLimit, setRetryLimit] = useState(0);
  const [stopPolicy, setStopPolicy] = useState<StopPolicy>({ kind: "never" });
  const [batch, setBatch] = useState<ProgrammingBatch | null>(null);
  const [stopping, setStopping] = useState(false);
  const [runContext, setRunContext] = useState<RunContext | null>(null);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const [startUnknown, setStartUnknown] = useState<string | null>(null);
  const [unresolved, setUnresolved] = useState<ProgrammingRun | null>(null);
  const [acknowledging, setAcknowledging] = useState(false);
  // null until the stored holds are read: nothing may start before that.
  const [startHolds, setStartHolds] = useState<Record<string, StartHold> | null>(null);
  const [releasingHold, setReleasingHold] = useState(false);
  // The explicit second operator step the Manager's last answer asked for.
  const [holdStep, setHoldStep] = useState<HoldStep | null>(null);
  const [statusNote, setStatusNote] = useState<string | null>(null);

  // READ: an independent Job per Site row, never part of the Batch above.
  const [readPhase, setReadPhase] = useState<ReadPhase>("idle");
  const [readSiteId, setReadSiteId] = useState<number | null>(null);
  const [siteReads, setSiteReads] = useState<Record<number, SiteRead>>({});

  const [logs, setLogs] = useState<EngineeringLogEntry[]>([]);
  const [clock, setClock] = useState(() => Date.now());
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [jobCollapsed, setJobCollapsed] = useState(false);

  const startLock = useRef(false);
  const loggedAttempts = useRef(new Map<number, string>());
  const loggedBatchId = useRef<string | null>(null);
  const readUrls = useRef(new Map<number, string>());
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

  useEffect(() => () => {
    abortRef.current?.abort();
    for (const url of readUrls.current.values()) URL.revokeObjectURL(url);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setStartHolds(readStartHolds()), 0);
    // A hold taken in another tab of this Browser blocks this tab too.
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === START_HOLD_KEY) setStartHolds({ ...readStartHolds() });
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

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
  const startHold = ppu && startHolds ? startHolds[ppu.alias] ?? null : null;
  const reading = readPhase !== "idle";
  // One Site, one Job: a Batch run and a READ Job lock each other out.
  const active = phase !== "idle" || reading;

  const capabilities = useMemo(
    () => new Map((ppu?.sites ?? []).map(site => [site.site_id, siteCapability(site, routes, icpn)] as const)),
    [ppu, routes, icpn],
  );
  // A Site stays selected only while it is programmable for the selected IC.
  const siteIds = useMemo(
    () => chosenSiteIds.filter(id => capabilities.get(id)?.programmable).sort((left, right) => left - right),
    [chosenSiteIds, capabilities],
  );
  // Only Operations a committed Route Profile declares can be selected, and a
  // Batch is one list for every Site in it: an Operation only SOME Sites
  // declare is not offered, because the Manager would refuse that Site alone.
  const declaredOperations = useMemo(() => {
    if (!siteIds.length) return routeSequenceOperations(routes, icpn, null);
    return siteIds
      .map(id => routeSequenceOperations(routes, icpn, id))
      .reduce((shared, declared) => shared.filter(item => declared.includes(item)));
  }, [routes, icpn, siteIds]);
  const selectedOperations = SEQUENCE_OPERATIONS.filter(
    item => checkedOperations[item] && declaredOperations.includes(item));
  const operations = normalizeOperations(selectedOperations);
  const needsImage = operations != null && operationsTakeImage(operations);
  // One Route per selected Site. A Site without one is not programmable here.
  const jobRoutes = useMemo(
    () => (operations ? siteIds.map(id => routeDeclaring(routes, icpn, id, operations)) : []),
    [operations, siteIds, routes, icpn],
  );
  const jobRoute = jobRoutes.length && jobRoutes.every(route => route != null) ? jobRoutes[0] : null;
  // Erase carries ONE range for the whole Batch, so every selected Site must
  // declare the same Flash range; otherwise the range would be wrong for one.
  const rangesAgree = jobRoute != null && jobRoutes.every(
    route => route?.flash_base === jobRoute.flash_base && route?.flash_size === jobRoute.flash_size);

  // What a Batch run and a READ Job both need of the PPU, before any Site.
  const ppuBlock: Readiness | null = (() => {
    if (phase !== "idle") return notReady("RUNNING", "A programming run is in progress; this selection is locked.");
    if (reading) return notReady("READING", "A READ Job is in progress on this PPU.");
    if (connection !== "online" || !topology) {
      return notReady("MANAGER OFFLINE", topologyError ?? "Connecting to the Manager Registry.");
    }
    if (!ppu) return notReady("NO PPU", "No commissioned PPU is registered. Register one in PPU → Registration.");
    if (!startHolds) return notReady("CHECKING", "Checking for an unreconciled Start request.");
    if (startHold) {
      return notReady("OUTCOME UNKNOWN",
        `A ${startHold.kind} Start request on this PPU has an unknown outcome. Nothing is submitted to this PPU until it is reconciled and acknowledged.`);
    }
    const unavailable = fromAvailability(ppu.availability) ?? fromAvailability(platformState)
      ?? fromAvailability(routesAvailability(routesState));
    if (unavailable) return unavailable;
    if (unresolved && unresolved.ppu_alias === ppu.alias && !unresolved.acknowledged) {
      return notReady("OUTCOME UNKNOWN",
        "The previous run on this PPU ended OUTCOME UNKNOWN. Reconcile the PPU and acknowledge it; nothing is resubmitted.");
    }
    if (!icpn) return notReady("NO TARGET", "Select a Target IC.");
    if (!routeSites(routes, icpn).length) {
      return notReady("NO ROUTE", `No Programming Route declares ${icpn}; this IC cannot be programmed on a managed PPU yet.`);
    }
    return null;
  })();
  const baseBlock = ppuBlock
    ?? (!siteIds.length ? notReady("NO SITE", `Select at least one Site qualified for ${icpn}.`) : null);

  const readiness: Readiness = (() => {
    if (baseBlock) return baseBlock;
    if (!declaredOperations.length) {
      return notReady("OPERATIONS UNAVAILABLE",
        `No Programming Route declares Erase, Program or Verify for ${icpn} on this Site.`);
    }
    if (!selectedOperations.length) return notReady("NO OP", "Select at least one of Erase, Program and Verify.");
    if (!operations) {
      return notReady("OPERATIONS INVALID",
        "Erase + Verify without Program is not supported: Verify compares the IC with the Programming Image, "
        + "which an erased IC can never equal. Add Program, or run Erase alone (it proves the range blank).");
    }
    if (!jobRoute) {
      const missing = siteIds.filter((_id, index) => jobRoutes[index] == null).map(siteLabel).join(", ");
      return notReady("NO ROUTE",
        `No single Programming Route declares ${operations.join(" + ")} for ${icpn} on ${missing || "this Site"}.`);
    }
    if (!needsImage && !rangesAgree) {
      return notReady("RANGE DIFFERS",
        "The selected Sites declare different Flash ranges. An Erase Batch carries one range for every "
        + "Site, so run them as separate Batches.");
    }
    if (!needsImage) return { ready: true, label: "BATCH READY", reason: "" };
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

  /** Why READ is unavailable on this Site right now; null when it can start. */
  function readBlockReason(id: number): string | null {
    if (ppuBlock) return ppuBlock.reason;
    const capability = capabilities.get(id);
    return capability?.programmable ? null : capability?.reason ?? "The Site is not available.";
  }

  function dropSiteRead(id: number) {
    const url = readUrls.current.get(id);
    if (url) URL.revokeObjectURL(url);
    readUrls.current.delete(id);
    setSiteReads(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }

  function clearReadState() {
    for (const url of readUrls.current.values()) URL.revokeObjectURL(url);
    readUrls.current = new Map();
    setSiteReads({});
  }

  function holdStart(alias: string, sites: number[], kind: StartHold["kind"], detail: string, identity: StartIdentity | null) {
    const next = { ...readStartHolds(), [alias]: {
      alias, siteIds: [...sites], kind, detail, at: new Date().toISOString(),
      startId: identity?.startId ?? null, jobBindingSha256: identity?.jobBindingSha256 ?? null,
    } };
    writeStartHolds(next);
    setStartHolds(next);
    setHoldStep(null);
  }

  // Operator reconciliation of a lost Start answer, decided by the Manager.
  // Every click asks the Manager (read-only) what became of that exact start.
  // The hold is released only when the Manager proves the start was never
  // admitted, or names the run / Batch it became with a definite result or an
  // acknowledged OUTCOME UNKNOWN, AND the Site is idle with no Job. A Site
  // being idle is never enough. The two writes (acknowledge the Manager run,
  // void an unstarted start) are separate explicit operator clicks and are
  // only sent when the fresh answer still asks for them.
  async function reconcileStartHold(step: "RECONCILE" | HoldStep["action"]) {
    if (!startHold || releasingHold || active) return;
    const hold = startHold;
    const label = `${hold.kind} Start ${hold.startId ?? "without a Manager start ID"} on PPU ${hold.alias}`;
    const keep = (why: string) => {
      setStatusNote(`The Start hold on PPU ${hold.alias} was kept: ${why}.`);
      appendLog(`[RECONCILE] HOLD KEPT · ${label} · ${why}`, true, "USR");
    };
    setReleasingHold(true);
    try {
      if (!hold.startId) {
        setHoldStep(null);
        keep("it was recorded without a Manager start ID, so the Manager cannot reconcile it");
        return;
      }
      const held = { ...hold, siteIds: holdSites(hold) };
      let answer = await getStartReconciliation(hold.startId);
      let decision = decideStartReconciliation(held, answer);
      if (step === "ACKNOWLEDGE_RUN" && decision.action === "ACKNOWLEDGE_RUN") {
        const runId = decision.runId;
        const acknowledged = await acknowledgeProgrammingRun(hold.alias, runId);
        setUnresolved(current => current?.run_id === runId && acknowledged.acknowledged ? null : current);
        appendLog(`[ACK] OUTCOME UNKNOWN reconciled by the operator · Run ${runId} · the device result stays unknown`, false, "USR");
        answer = await getStartReconciliation(hold.startId);
        decision = decideStartReconciliation(held, answer);
      } else if (step === "VOID" && decision.action === "VOID") {
        answer = await voidStart(hold.startId, hold.alias);
        appendLog(`[VOID] ${label} was voided on the Manager before admission; it can never start`, false, "USR");
        decision = decideStartReconciliation(held, answer);
      }
      setHoldStep(decision.action === "ACKNOWLEDGE_RUN" || decision.action === "VOID"
        ? { startId: hold.startId, action: decision.action } : null);
      if (decision.action !== "RELEASE") {
        keep(decision.summary);
        return;
      }
      const fresh = await loadManagedTopology();
      setTopology(fresh);
      const target = fresh.ppus.find(item => item.alias === hold.alias);
      // EVERY Site the lost Start was for must read idle. One busy Site is
      // enough to keep the hold: the Manager may still be on it.
      const siteRefusal = holdSites(held).map(id => {
        const site = target?.sites.find(item => item.site_id === id);
        if (!site || !site.enabled) return `${siteLabel(id)} is not reported enabled by the PPU`;
        if (site.current_job_id || site.state !== "idle") {
          return `${siteLabel(id)} is ${site.state.toUpperCase()}${site.current_job_id ? ` (Job ${site.current_job_id})` : ""}`;
        }
        return null;
      }).find(reason => reason != null) ?? null;
      const refusal = !target ? "the PPU is not in the Manager Registry"
        : !target.availability.ready ? `${target.availability.label} — ${target.availability.reason}`
        : siteRefusal;
      if (refusal) {
        keep(`${decision.summary}, but ${refusal}`);
        return;
      }
      const next = { ...readStartHolds() };
      delete next[hold.alias];
      writeStartHolds(next);
      setStartHolds(next);
      setStatusNote(null);
      appendLog(`[RECONCILE] ${label} reconciled with the Manager · ${decision.summary} · ${holdSites(held).map(siteLabel).join(", ") || "no Site recorded"} idle, no Job (Manager Fleet)`, false, "USR");
    } catch (reason) {
      keep(`the Manager could not be asked (${reason instanceof Error ? reason.message : "request failed"})`);
    } finally {
      setReleasingHold(false);
    }
  }

  function clearRunState() {
    setLocked(null);
    setBatch(null);
    loggedAttempts.current = new Map();
    loggedBatchId.current = null;
    setRun(null);
    setRunContext(null);
    setBlockedMessage(null);
    setStartUnknown(null);
    setStatusNote(null);
  }

  function selectAlias(alias: string | null) {
    if (active || alias === selectedAlias) return;
    setSelectedAlias(alias);
    setChosenSiteIds([]);
    clearRunState();
    clearReadState();
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
    clearReadState();
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

  function toggleOperation(item: SequenceOperation) {
    if (active) return;
    const next = { ...checkedOperations, [item]: !checkedOperations[item] };
    setCheckedOperations(next);
    clearRunState();
    const list = SEQUENCE_OPERATIONS.filter(name => next[name] && declaredOperations.includes(name));
    appendLog(`[OPS] ${list.length ? list.map(name => name.toUpperCase()).join(" → ") : "none"}`, false, "USR");
  }

  function toggleSite(id: number) {
    if (active) return;
    const next = chosenSiteIds.includes(id)
      ? chosenSiteIds.filter(item => item !== id)
      : [...chosenSiteIds, id].sort((left, right) => left - right);
    setChosenSiteIds(next);
    clearRunState();
    // A Batch over fewer Sites than before can no longer reach the old
    // threshold, so the Stop Policy falls back to the Batch's Site count.
    setStopPolicy(current => (current.kind === "failed_sites" && current.threshold > next.length
      ? (next.length ? { kind: "failed_sites", threshold: next.length } : { kind: "never" })
      : current));
    appendLog(`[SITE] SELECTION · ${next.length ? next.map(siteLabel).join(", ") : "none"}`, false, "USR");
  }

  async function start() {
    // Double-click protection: the lock is taken synchronously, before any await.
    if (startLock.current || !readiness.ready || !ppu || !siteIds.length || !icpn || !operations || !jobRoute
      || (needsImage && !file)) return;
    startLock.current = true;
    const policy = { retryLimit, stopPolicy };
    const started = [...siteIds];
    const request: ManagedBatchRequest = needsImage && file
      ? { alias: ppu.alias, siteIds: started, icpn, operations, source, file, ...policy }
      // Erase only: no Programming Image; the whole Flash range of the Profile.
      : {
        alias: ppu.alias, siteIds: started, icpn, operations: ["erase"], source, file: null,
        range: { address: jobRoute.flash_base, length: jobRoute.flash_size }, ...policy,
      };
    const operationLabel = operations.map(item => item.toUpperCase()).join(" → ");
    // Site interface the PPU reports: a Mock result is never hardware evidence.
    // Per Site: the interface the PPU reports for the Site that actually ran.
    // A Mock result is never hardware evidence, whichever Site produced it.
    const sites = ppu.sites;
    const interfaceOf = (siteId: number) => sites.find(item => item.site_id === siteId)?.interface ?? null;
    const context: RunContext = { alias: ppu.alias, siteIds: started, startedAt: wallClock(), finishedAt: null };
    const abort = new AbortController();
    abortRef.current = abort;
    clearRunState();
    setRunContext(context);
    setPhase("locking");
    appendLog(`[START] ${operationLabel} · PPU ${ppu.alias} (${ppu.ppuId ?? "—"}) · ${started.map(siteLabel).join(", ")} (${started.length} Site${started.length === 1 ? "" : "s"}) · ${icpn} · ${
      request.file ? `${source.toUpperCase()} ${request.file.name}` : `no Programming Image · ${hex(request.range.address)} + ${request.range.length} B`
    } · Retry ${retryLimit} · Stop Policy ${stopPolicy.kind === "never" ? "never" : `${stopPolicy.threshold} failed Site${stopPolicy.threshold === 1 ? "" : "s"}`} · Repeat 1 · sequential`, false, "USR");
    try {
      const final = await runManagedBatch(request, {
        onLocked: input => {
          setLocked(input);
          setPhase("planning");
          appendLog(`[LOCK] ${input.source.toUpperCase()} · ${input.name} · ${input.size} B · SHA256 ${input.sha256}`, false, "DAT");
        },
        onBatch: next => {
          if (loggedBatchId.current !== next.batch_id) {
            loggedBatchId.current = next.batch_id;
            appendLog(`[BATCH] ${next.batch_id} · ${next.counts.sites} Site(s) · Repeat ${next.policy.repeat} · Retry limit ${next.policy.retry_limit} · Stop Policy ${
              next.policy.stop_policy.kind === "never"
                ? "never"
                : `${next.policy.stop_policy.threshold} failed Site(s)`}`, false, "BAT");
          }
          setBatch(next);
          setRun(next.current_run);
          setPhase(next.attempts.length ? "running" : "starting");
          setStatusNote(null);
          // The Backend plan runs for every attempt; its technical result lives
          // in the Log and in Receipts & Diagnostics, not in a standing panel.
          for (const attempt of next.attempts) {
            const seen = loggedAttempts.current.get(attempt.attempt);
            if (seen === undefined) {
              loggedAttempts.current.set(attempt.attempt, "planned");
              appendLog(`[ATTEMPT ${attempt.attempt}/${next.policy.retry_limit + 1}] Plan ${attempt.plan_id} · Job Binding SHA256 ${attempt.job_binding_sha256}`, false, "DAT");
              const planned = next.current_run?.plan;
              if (planned?.plan_id === attempt.plan_id) {
                const range = planned.job_binding.range;
                appendLog(`[PLAN] ${planned.plan_id} · Route ${planned.route.route_id} (${planned.route.provider} → ${planned.route.profile}) · Source ${planned.source} · Operations ${(planned.operations ?? [planned.operation]).join(" → ")}`, false, "DAT");
                appendLog(`[PLAN] Range ${hex(range.address)} + ${range.length} B · Resource SHA256 ${planned.resource.resource_set_sha256} · Job Binding SHA256 ${planned.job_binding_sha256}`, false, "DAT");
                appendLog(`[PLAN] ${planned.activation_required ? "Activation: B1 upload → B2 admit → B3 activate (no FPGA load)" : "Resource Reuse: the PPU verified identical Programming Resources (no B1/B2/B3, no FPGA load)"}`, false, "DAT");
              }
            }
            if (attempt.outcome && seen !== "finished") {
              loggedAttempts.current.set(attempt.attempt, "finished");
              const retry = attempt.retry ? ` · ${attempt.retry.decision === "RETRY" ? "RETRY" : "NO RETRY"} (${attempt.retry.reason})` : "";
              appendLog(`[ATTEMPT ${attempt.attempt}/${next.policy.retry_limit + 1}] ${attempt.outcome.replace("_", " ")}${attempt.reason ? ` · ${attempt.reason}` : ""} · Run ${attempt.run_id ?? "—"} · Job ${attempt.job_id ?? "—"} · SAFE_OFF ${safeOffLogLabel(attempt.safe_off, true)}${retry}`,
                attempt.outcome !== "PASS", "PPU");
              // The Log is the only on-screen operation record: the Manager run
              // identities and its Receipt summary, never the whole JSON Receipt.
              const finishedRun = next.current_run?.run_id === attempt.run_id ? next.current_run : null;
              if (finishedRun) {
                for (const line of programmingRunLogLines(finishedRun, {
                  executionInterface: interfaceOf(finishedRun.site_id),
                })) {
                  appendLog(line, attempt.outcome !== "PASS", "PPU");
                }
              }
            }
          }
        },
        onPollError: message => setStatusNote(message),
      }, abort.signal);
      const { verdict, reason } = batchVerdict(final);
      for (const unit of final.units) {
        const site = batchSiteVerdict(final, unit, runOfUnit(final, unit));
        appendLog(`[SITE RESULT] ${siteLabel(unit.site_id)} · ${site.verdict.replace("_", " ")}${site.reason ? ` · ${site.reason}` : ""}${
          unit.failure_domain ? ` · ${unit.failure_domain}` : ""} · ${unit.attempts.length} attempt(s)`,
          site.verdict !== "PASS", "PPU");
      }
      appendLog(`[RESULT] ${verdict.replace("_", " ")}${reason ? ` · ${reason}` : ""} · Batch ${final.batch_id} · ${
        final.counts.sites} Site(s) · PASS ${final.counts.pass} · FAIL ${final.counts.fail} · BLOCKED ${
        final.counts.blocked} · UNKNOWN ${final.counts.unknown} · ${final.attempts.length} attempt(s) · one IC per Site`,
        verdict !== "PASS", "PPU");
      if (final.outcome === "OUTCOME_UNKNOWN" && final.current_run) setUnresolved(final.current_run);
    } catch (reason) {
      if (reason instanceof ManagedProgrammingBlocked) {
        const message = describeBlocked(reason);
        setBlockedMessage(message);
        appendLog(`[BLOCKED] ${reason.stage.toUpperCase()} · ${message} · no Job was submitted`, true);
      } else if (reason instanceof ManagedStartOutcomeUnknown) {
        setStartUnknown(reason.message);
        holdStart(context.alias, context.siteIds, "PROGRAMMING", reason.message, reason.identity);
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

  // Stop queuing: no further attempt is submitted. A submitted Job is never
  // cancelled, its lease never released and the PPU never reset by this.
  async function stopQueuing() {
    if (!batch || batch.outcome != null || batch.stop_requested || stopping) return;
    setStopping(true);
    try {
      const next = await stopProgrammingBatch(batch.batch_id);
      setBatch(next);
      appendLog(`[STOP QUEUING] Batch ${next.batch_id} · no further attempt will be submitted · the running Job is not cancelled`, false, "USR");
    } catch (reason) {
      setStatusNote(`Stop queuing failed: ${reason instanceof Error ? reason.message : "request failed"}`);
    } finally {
      setStopping(false);
    }
  }

  // READ on one Site row: choose the destination first, then one independent
  // Job over the whole Flash range of the Programming Route. Cancelling the
  // Save File Picker submits nothing.
  async function readSite(id: number) {
    const route = routeDeclaring(routes, icpn, id, ["read"]);
    // Same synchronous lock as Start: a double click never submits twice.
    if (startLock.current || readBlockReason(id) != null || !ppu || !icpn || !route) return;
    startLock.current = true;
    const alias = ppu.alias;
    const address = route.flash_base;
    const length = route.flash_size;
    const label = siteLabel(id);
    const suggestedName = `read-${icpn}-${alias}-site${id}.bin`.replace(/[^A-Za-z0-9._-]/g, "_");
    const finish = (status: SiteRead["status"], detail: string, download: SiteRead["download"] = null) => {
      if (download) readUrls.current.set(id, download.url);
      setSiteReads(current => ({ ...current, [id]: { status, detail, download } }));
    };
    const offerDownload = (data: Uint8Array, filename: string) => ({
      url: URL.createObjectURL(new Blob([data.slice().buffer], { type: "application/octet-stream" })),
      filename,
    });
    dropSiteRead(id);
    setReadSiteId(id);
    setReadPhase("choosing");
    try {
      let handle: FileSystemFileHandle | null = null;
      const picker = saveFilePicker();
      if (picker) {
        try {
          handle = await picker({
            suggestedName,
            types: [{ description: "Binary image", accept: { "application/octet-stream": [".bin"] } }],
          });
        } catch (reason) {
          if ((reason as { name?: string } | null)?.name === "AbortError") {
            appendLog(`[READ] CANCELLED · ${label} · no file was chosen · no Job was submitted`, false, "USR");
            return;
          }
          const detail = reason instanceof Error ? reason.message : "unknown error";
          if ((reason as { name?: string } | null)?.name !== "SecurityError") {
            // Permission denied (or any other refusal): the destination was not granted, so nothing is read.
            finish("BLOCKED", `The Save File Picker was refused: ${detail}. No Job was submitted.`);
            appendLog(`[READ] BLOCKED · ${label} · the Save File Picker was refused (${detail}) · no Job was submitted`, true);
            return;
          }
          appendLog(`[READ] ${label} · this Browser blocks the Save File Picker here (${detail}) · the verified binary will be offered as a download`, true);
        }
      } else {
        appendLog(`[READ] ${label} · this Browser has no Save File Picker · the verified binary will be offered as a download`, false, "SYS");
      }
      const abort = new AbortController();
      abortRef.current = abort;
      setReadPhase("planning");
      appendLog(`[READ] START · PPU ${alias} · ${label} · ${icpn} · ${hex(address)} + ${length} B (whole Flash) · ${
        handle ? `save to ${handle.name}` : "Browser download"} · independent Job, not part of the Batch`, false, "USR");
      const result = await runManagedRead({ alias, siteId: id, icpn, address, length }, {
        onPlan: next => appendLog(`[READ] PLAN ${next.plan_id} · Route ${next.route.route_id} · Job Binding SHA256 ${next.job_binding_sha256}`, false, "DAT"),
        onRun: next => setReadPhase(next.outcome == null ? "running" : "saving"),
        onPollError: message => setStatusNote(message),
      }, abort.signal);
      const { verdict, reason } = runVerdict(result.run);
      const output = result.run.receipt?.read_output ?? null;
      appendLog(`[READ] ${verdict.replace("_", " ")}${reason ? ` · ${reason}` : ""} · ${label} · Run ${result.run.run_id} · Job ${result.run.receipt?.job_id ?? "—"} · SAFE_OFF ${
        result.run.receipt?.safe_off === true ? "VERIFIED" : "NOT VERIFIED"}${
        output ? ` · ${output.bytes} B · SHA256 ${output.sha256 ?? "—"}` : ""}${result.downloadError ? ` · binary rejected: ${result.downloadError}` : ""}`,
        verdict !== "PASS" || Boolean(result.downloadError), "PPU");
      if (result.run.outcome === "OUTCOME_UNKNOWN") setUnresolved(result.run);
      if (verdict !== "PASS") {
        finish(verdict === "RUNNING" ? "FAIL" : verdict === "OUTCOME_UNKNOWN" ? "OUTCOME UNKNOWN" : verdict,
          reason ?? "The READ Job did not pass.");
        if (handle) appendLog(`[READ] ${label} · nothing was written to ${handle.name}`, true);
        return;
      }
      if (!result.data) {
        // PASS without bytes that re-hash to the receipt SHA256 is not a usable READ.
        finish("FAIL", result.downloadError ?? "No verified binary is available.");
        if (handle) appendLog(`[READ] ${label} · nothing was written to ${handle.name}`, true);
        return;
      }
      const filename = output?.filename ?? suggestedName;
      if (!handle) {
        finish("PASS", "SHA256 verified. Use SAVE to download the binary.", offerDownload(result.data, filename));
        appendLog(`[READ] ${label} · ${result.data.length} B verified · offered as Browser download ${filename}`, false, "DAT");
        return;
      }
      try {
        const writable = await handle.createWritable();
        await writable.write(new Blob([result.data.slice().buffer], { type: "application/octet-stream" }));
        await writable.close();
        finish("PASS", `SHA256 verified; saved to ${handle.name}.`);
        appendLog(`[READ] SAVED · ${label} · ${handle.name} · ${result.data.length} B · SHA256 ${output?.sha256 ?? "—"}`, false, "DAT");
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : "write failed";
        finish("SAVE FAILED", `The verified binary could not be written to ${handle.name}: ${message}. Use SAVE to download it.`,
          offerDownload(result.data, filename));
        appendLog(`[READ] SAVE FAILED · ${label} · ${handle.name} · ${message} · the verified binary is offered as a download instead`, true);
      }
    } catch (reason) {
      const blocked = reason instanceof ManagedProgrammingBlocked;
      const unknown = reason instanceof ManagedStartOutcomeUnknown;
      const message = blocked ? `Not started — ${describeBlocked(reason)}`
        : unknown ? `OUTCOME UNKNOWN — ${reason.message} Check the PPU before reading again.`
        : reason instanceof Error ? reason.message : "READ failed";
      finish(blocked ? "BLOCKED" : unknown ? "OUTCOME UNKNOWN" : "FAIL", message);
      // A lost Start answer is not a FAIL: hold every further Start on this PPU.
      if (unknown) holdStart(alias, [id], "READ", reason.message, reason.identity);
      appendLog(`[READ] ${label} · ${message}`, true);
    } finally {
      setReadPhase("idle");
      setReadSiteId(null);
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

  // One Site is one IC: counted once by its own final verdict, whatever the
  // attempts. The Batch verdict is the aggregate and never a Site's result.
  const verdict = batch ? batchVerdict(batch).verdict : null;
  const siteVerdicts = batch
    ? batch.units.map(unit => batchSiteVerdict(batch, unit, runOfUnit(batch, unit)).verdict)
    : [];
  const pass = siteVerdicts.filter(item => item === "PASS").length;
  const fail = siteVerdicts.filter(item => item === "FAIL").length;
  const siteCount = batch ? batch.counts.sites : (runContext?.siteIds.length ?? siteIds.length);
  const elapsed = runContext ? (runContext.finishedAt ?? clock) - runContext.startedAt : null;
  const kpis = [
    { key: "sites", label: "SITES", value: siteCount },
    { key: "total-ic", label: "TOTAL IC", value: siteCount },
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
    : operations && !needsImage
      ? "Erase only: no Programming Image is used; the Flash range of the Programming Profile is erased and proven blank."
    : source === "bundle"
      ? "Your own canonical Bundle v3. The Manager verifies it against the qualified Programming Route."
      : "Binary Programming Image (.bin). The Manager builds the canonical Bundle v3.";
  const policyNote = locale === "zh-TW"
    ? `每次 Attempt 為獨立 Job（attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}）。Retry：僅在明確 FAIL、SAFE_OFF 已驗證且 Site 已釋放時，由 Manager 以新的 Plan／Job 重試；OUTCOME UNKNOWN 永不重送。Stop Policy 與 STOP QUEUING 只停止尚未提交的 Attempt，不取消執行中的 Job。Repeat 固定為 1（暫不實作）。`
    : `Each attempt is its own Job (attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}). Retry: the Manager submits a new Plan / Job only after a definite FAIL with SAFE_OFF verified and the Site released; OUTCOME UNKNOWN is never resubmitted. Stop Policy and STOP QUEUING only stop attempts that are not submitted yet; a running Job is never cancelled. Repeat is fixed at 1 (not implemented).`;
  const fileDetails = file ? `${formatBytes(file.size)} · ${fileFormat(file, source)}` : null;
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
            <OperatorPanelHeader
              number={1}
              title="SYSTEM SETUP & TARGETING"
              actions={(
                <button
                  type="button"
                  className="engineeringPanelToggle"
                  aria-label={`${setupCollapsed ? "Expand" : "Collapse"} System Setup`}
                  aria-expanded={!setupCollapsed}
                  onClick={() => setSetupCollapsed(current => !current)}
                >{setupCollapsed ? "展開⌄" : "收合⌃"}</button>
              )}
            />
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
                details: fileDetails,
                browseLabel: file ? "Change..." : "Browse...",
                browseDisabled: active,
                inputDisabled: active,
                inputAriaLabel: `Engineering Programming ${sourceLabel} file`,
                accept: PROGRAMMING_SOURCE_ACCEPT[source],
                onFileChange: next => selectFile(next),
              }}
              operationsLabel="Operations"
              operations={SEQUENCE_OPERATIONS.map(item => ({
                key: item,
                code: OPERATION_LABELS[item].code,
                label: OPERATION_LABELS[item].label,
                // An Operation no Route declares stays unchecked and disabled: never a fake capability.
                checked: checkedOperations[item] && (declaredOperations.includes(item) || !siteIds.length),
                disabled: active || (siteIds.length > 0 && !declaredOperations.includes(item)),
                ariaLabel: `Engineering operation ${item}`,
                onChange: () => toggleOperation(item),
              }))}
              policyLabel="Batch Policy"
              policy={{
                repeatLabel: "Repeat",
                repeatValue: String(MANAGED_JOB_POLICY.attempts),
                repeatDisabled: true,
                repeatAriaLabel: "Repeat Count",
                onRepeatChange: () => {},
                retryLabel: "Retry",
                retryValue: String(retryLimit),
                retryDisabled: active,
                retryMax: MAX_RETRY_LIMIT,
                retryAriaLabel: "Site Retry Limit",
                onRetryChange: value => {
                  const parsed = Number.parseInt(value, 10);
                  setRetryLimit(Number.isFinite(parsed) ? Math.min(MAX_RETRY_LIMIT, Math.max(0, parsed)) : 0);
                },
                stopLabel: "Stop Policy",
                stopValue: stopPolicy.kind === "never" ? "never" : String(stopPolicy.threshold),
                stopDisabled: active,
                stopAriaLabel: "Engineering Stop Policy",
                // A threshold no Batch could reach is not a policy: the list
                // stops at the number of Sites this Batch actually covers.
                stopOptions: [
                  { value: "never", label: "Never" },
                  ...siteIds.map((_id, index) => ({
                    value: String(index + 1),
                    label: `${index + 1} failed Site${index === 0 ? "" : "s"}`,
                  })),
                ],
                onStopChange: value => {
                  const threshold = Number.parseInt(value, 10);
                  setStopPolicy(Number.isFinite(threshold) && threshold >= 1 && threshold <= siteIds.length
                    ? { kind: "failed_sites", threshold }
                    : { kind: "never" });
                },
                note: policyNote,
              }}
              startLabel="START PROGRAMMING"
              startDisabled={!readiness.ready}
              onStart={start}
              statusLabel="BATCH STATUS"
              statusValue={phaseLabel}
              statusClassName={`readiness-${readiness.ready ? "batch-ready" : phase !== "idle" ? "running" : "programming-unavailable"}`}
              abortLabel={batch?.stop_requested && batch.outcome == null ? "STOP REQUESTED" : "STOP QUEUING"}
              abortDisabled={!batch || batch.outcome != null || batch.stop_requested || stopping}
              onAbort={stopQueuing}
            />

            {!readiness.ready && phase === "idle" && (
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
            {startHold && (
              <div className="warning engineeringOperationWarning" role="alert" data-testid="managed-start-hold">
                <span>
                  OUTCOME UNKNOWN — the {startHold.kind} Start request on PPU {startHold.alias} · {holdSites(startHold).map(siteLabel).join(", ") || "no Site recorded"} got
                  no answer ({startHold.detail}) It may or may not have reached the PPU. Nothing is submitted to this PPU
                  until the Manager reconciles Start {startHold.startId ?? "(no Manager start ID recorded)"}.
                </span>
                <button type="button" className="engineeringAcknowledge" disabled={releasingHold || active} onClick={() => void reconcileStartHold("RECONCILE")}>
                  Reconcile Start with Manager
                </button>
                {holdStep && holdStep.startId === startHold.startId && (
                  <button type="button" className="engineeringAcknowledge" data-testid="managed-start-hold-step"
                    disabled={releasingHold || active} onClick={() => void reconcileStartHold(holdStep.action)}>
                    {holdStep.action === "VOID" ? "Void the unstarted Start" : "Acknowledge Run reconciliation"}
                  </button>
                )}
              </div>
            )}
            {statusNote && <div className="warning engineeringOperationWarning" role="status" data-testid="managed-status-note">{statusNote}</div>}
          </div>
        </div>

        {unresolved && !unresolved.acknowledged && (
          <div className="warning engineeringOperationWarning" role="alert" data-testid="managed-unresolved">
            <span>
              Run {unresolved.run_id} on PPU {unresolved.ppu_alias} ended OUTCOME UNKNOWN. Nothing was resubmitted.
              Reconcile the PPU through the normal recovery procedure, then acknowledge.
            </span>
            <button type="button" className="engineeringAcknowledge" disabled={acknowledging} onClick={() => void acknowledge()}>Acknowledge reconciliation</button>
          </div>
        )}

        <section className="productionProgrammingCard liveSiteStatus overviewCard" aria-label="Engineering Site status">
          <OperatorPanelHeader
            number={3}
            title="LIVE SITE STATUS"
            meta={`${ppu?.displayName ?? "Selected PPU"} · ${ppu?.sites.length ?? 0} Sites · Selected ${siteIds.length} · sequential · Manager Fleet polling ${TOPOLOGY_POLL_MS / 1000} s`}
          />
          <div className="channelTableWrap engineeringV2TableWrap" role="region" aria-label="Engineering Site selection">
            <table className="channelTable">
              <thead>
                <tr><th>SELECT</th><th>SITE</th><th>TARGET IC</th><th>STATE</th><th>PROGRESS</th><th>RESULT</th><th>READ</th><th>PROGRAMMING CAPABILITY</th></tr>
              </thead>
              <tbody className="targetSitesSection">
                {(ppu?.sites ?? []).map(site => {
                  const capability = capabilities.get(site.site_id);
                  const selected = siteIds.includes(site.site_id);
                  const unit = batch?.units.find(item => item.site_id === site.site_id
                    && item.ppu_alias === (ppu?.alias ?? "")) ?? null;
                  // The run the Browser holds belongs to ONE Site at a time:
                  // the Batch is sequential, so another Site's row shows none.
                  const siteRun = run != null && runContext?.alias === ppu?.alias
                    && run.site_id === site.site_id && run.ppu_alias === ppu?.alias ? run : null;
                  const progress = siteRun ? runProgressPercent(siteRun) : null;
                  // The Site result is that Site's own verdict, never the
                  // Batch aggregate and never an intermediate attempt.
                  const rowVerdict = batch && unit
                    ? batchSiteVerdict(batch, unit, runOfUnit(batch, unit)).verdict : null;
                  const state = siteRun && siteRun.outcome == null ? runStageLabel(siteRun)
                    : site.enabled ? site.state.toUpperCase() : "DISABLED";
                  // READ: one button per Site whose Programming Route declares Read.
                  const canRead = routeDeclaring(routes, icpn, site.site_id, ["read"]) != null;
                  const readBlocked = canRead ? readBlockReason(site.site_id) : null;
                  const readingHere = readSiteId === site.site_id && readPhase !== "idle" && readPhase !== "choosing";
                  const siteRead = siteReads[site.site_id] ?? null;
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
                      <td className="siteReadCell" data-testid={`site-read-${site.site_id}`}>
                        {canRead ? (
                          <button
                            type="button"
                            className="siteReadButton"
                            aria-label={`Read SITE ${site.site_id} Flash`}
                            title={readBlocked ?? "Read the whole Flash to a file (independent Job)"}
                            disabled={readBlocked != null}
                            onClick={() => void readSite(site.site_id)}
                          >{readingHere ? "READING" : "READ"}</button>
                        ) : <b>—</b>}
                        {siteRead && !readingHere && (
                          <b className="siteReadStatus" role="status" aria-label={`SITE ${site.site_id} Read status`}
                            data-read-status={siteRead.status} title={siteRead.detail}>{siteRead.status}</b>
                        )}
                        {siteRead?.download && !readingHere && (
                          <a className="siteReadDownload" href={siteRead.download.url} download={siteRead.download.filename}
                            aria-label={`Save SITE ${site.site_id} Read binary`}>SAVE</a>
                        )}
                      </td>
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
