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
  loadManagedTopology,
  loadPlatformAvailability,
  loadProgrammingRoutes,
  MANAGED_JOB_POLICY,
  ManagedProgrammingBlocked,
  ManagedStartOutcomeUnknown,
  platformAvailability,
  routeDeclaring,
  routesAvailability,
  routeSequenceOperations,
  routeSites,
  runManagedProgramming,
  runManagedRead,
  runProgressPercent,
  runStageLabel,
  runVerdict,
  siteCapability,
  type LockedInput,
  type ManagedAvailability,
  type ManagedRunRequest,
  type ManagedTopology,
  type ProgrammingRun,
  type ProgrammingSource,
  type RoutesState,
} from "../programming/managed-programming";
import {
  acknowledgeProgrammingRun,
  normalizeOperations,
  operationsTakeImage,
  SEQUENCE_OPERATIONS,
  type SequenceOperation,
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
type ReadPhase = "idle" | "planning" | "running" | "downloading";
type ReadResult = {
  run: ProgrammingRun;
  url: string | null;
  filename: string | null;
  downloadError: string | null;
};
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

/** Decimal or 0x-prefixed hexadecimal; null when it is not a non-negative integer. */
function parseInteger(text: string): number | null {
  const trimmed = text.trim();
  if (!/^(0x[0-9a-f]+|[0-9]+)$/i.test(trimmed)) return null;
  const value = Number(trimmed);
  return Number.isSafeInteger(value) ? value : null;
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
  const [checkedOperations, setCheckedOperations] = useState(ALL_OPERATIONS);

  const [phase, setPhase] = useState<Phase>("idle");
  const [locked, setLocked] = useState<LockedInput | null>(null);
  const [run, setRun] = useState<ProgrammingRun | null>(null);
  const [runContext, setRunContext] = useState<RunContext | null>(null);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const [startUnknown, setStartUnknown] = useState<string | null>(null);
  const [unresolved, setUnresolved] = useState<ProgrammingRun | null>(null);
  const [acknowledging, setAcknowledging] = useState(false);
  const [statusNote, setStatusNote] = useState<string | null>(null);

  // Read Memory: an independent Job, never part of the Batch above.
  const [readAddress, setReadAddress] = useState("");
  const [readLength, setReadLength] = useState("");
  const [readPhase, setReadPhase] = useState<ReadPhase>("idle");
  const [readRun, setReadRun] = useState<ProgrammingRun | null>(null);
  const [readResult, setReadResult] = useState<ReadResult | null>(null);
  const [readMessage, setReadMessage] = useState<string | null>(null);

  const [logs, setLogs] = useState<EngineeringLogEntry[]>([]);
  const [clock, setClock] = useState(() => Date.now());
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [jobCollapsed, setJobCollapsed] = useState(false);

  const startLock = useRef(false);
  const readUrl = useRef<string | null>(null);
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
    if (readUrl.current) URL.revokeObjectURL(readUrl.current);
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
  const reading = readPhase !== "idle";
  // One Site, one Job: a Batch run and a Read Memory Job lock each other out.
  const active = phase !== "idle" || reading;

  const capabilities = useMemo(
    () => new Map((ppu?.sites ?? []).map(site => [site.site_id, siteCapability(site, routes, icpn)] as const)),
    [ppu, routes, icpn],
  );
  // A Site stays selected only while it is programmable for the selected IC.
  const siteId = chosenSiteId != null && capabilities.get(chosenSiteId)?.programmable ? chosenSiteId : null;
  // Only Operations a committed Route Profile declares can be selected.
  const declaredOperations = useMemo(() => routeSequenceOperations(routes, icpn, siteId), [routes, icpn, siteId]);
  const selectedOperations = SEQUENCE_OPERATIONS.filter(
    item => checkedOperations[item] && declaredOperations.includes(item));
  const operations = normalizeOperations(selectedOperations);
  const needsImage = operations != null && operationsTakeImage(operations);
  const jobRoute = operations ? routeDeclaring(routes, icpn, siteId, operations) : null;
  const readRoute = routeDeclaring(routes, icpn, siteId, ["read"]);

  // What a Batch run and a Read Memory Job both need before anything else.
  const baseBlock: Readiness | null = (() => {
    if (phase !== "idle") return notReady("RUNNING", "A programming run is in progress; this selection is locked.");
    if (reading) return notReady("READING", "A Read Memory Job is in progress on this Site.");
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
    return null;
  })();

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
      return notReady("NO ROUTE", `No single Programming Route declares ${operations.join(" + ")} for ${icpn} on this Site.`);
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

  const readStart = parseInteger(readAddress.trim() || (readRoute ? hex(readRoute.flash_base) : ""));
  const readSize = parseInteger(readLength.trim() || (readRoute ? String(readRoute.flash_size) : ""));
  const readReadiness: Readiness = (() => {
    if (baseBlock) return baseBlock;
    if (!readRoute) return notReady("READ UNAVAILABLE", `No Programming Route declares Read for ${icpn} on this Site.`);
    if (readStart == null) return notReady("ADDRESS INVALID", "Start Address must be decimal or 0x hexadecimal.");
    if (readSize == null || readSize <= 0) return notReady("LENGTH INVALID", "Length must be a positive number of bytes.");
    const end = readRoute.flash_base + readRoute.flash_size;
    if (readStart < readRoute.flash_base || readStart + readSize > end) {
      return notReady("OUT OF RANGE",
        `Only the Flash range ${hex(readRoute.flash_base)}–${hex(end - 1)} of the Programming Profile can be read.`);
    }
    return { ready: true, label: "READ READY", reason: "" };
  })();

  function clearReadState() {
    if (readUrl.current) URL.revokeObjectURL(readUrl.current);
    readUrl.current = null;
    setReadRun(null);
    setReadResult(null);
    setReadMessage(null);
  }

  function clearRunState() {
    setLocked(null);
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
    const next = siteId === id ? null : id;
    setChosenSiteId(next);
    clearRunState();
    clearReadState();
    appendLog(`[SITE] SELECTION · ${next == null ? "none" : siteLabel(next)}`, false, "USR");
  }

  async function start() {
    // Double-click protection: the lock is taken synchronously, before any await.
    if (startLock.current || !readiness.ready || !ppu || siteId == null || !icpn || !operations || !jobRoute
      || (needsImage && !file)) return;
    startLock.current = true;
    const request: ManagedRunRequest = needsImage && file
      ? { alias: ppu.alias, siteId, icpn, operations, source, file }
      // Erase only: no Programming Image; the whole Flash range of the Profile.
      : {
        alias: ppu.alias, siteId, icpn, operations: ["erase"], source, file: null,
        range: { address: jobRoute.flash_base, length: jobRoute.flash_size },
      };
    const operationLabel = operations.map(item => item.toUpperCase()).join(" → ");
    const context: RunContext = { alias: ppu.alias, siteId, startedAt: Date.now(), finishedAt: null };
    const abort = new AbortController();
    abortRef.current = abort;
    clearRunState();
    setRunContext(context);
    setPhase("locking");
    appendLog(`[START] ${operationLabel} · PPU ${ppu.alias} (${ppu.ppuId ?? "—"}) · ${siteLabel(siteId)} · ${icpn} · ${
      request.file ? `${source.toUpperCase()} ${request.file.name}` : `no Programming Image · ${hex(request.range.address)} + ${request.range.length} B`
    }`, false, "USR");
    try {
      const final = await runManagedProgramming(request, {
        onLocked: input => {
          setLocked(input);
          setPhase("planning");
          appendLog(`[LOCK] ${input.source.toUpperCase()} · ${input.name} · ${input.size} B · SHA256 ${input.sha256}`, false, "DAT");
        },
        onPlan: next => {
          // The Backend plan always runs; its technical result lives in the Log
          // and in Receipts & Diagnostics, not in a standing panel.
          setPhase("starting");
          const range = next.job_binding.range;
          appendLog(`[PLAN] ${next.plan_id} · Route ${next.route.route_id} (${next.route.provider} → ${next.route.profile}) · Source ${next.source} · Operations ${(next.operations ?? [next.operation]).join(" → ")}`, false, "DAT");
          appendLog(`[PLAN] Range ${hex(range.address)} + ${range.length} B · Resource SHA256 ${next.resource.resource_set_sha256} · Job Binding SHA256 ${next.job_binding_sha256}`, false, "DAT");
          appendLog(`[PLAN] ${next.activation_required ? "Activation: B1 upload → B2 admit → B3 activate (no FPGA load)" : "Resource Reuse: the PPU verified identical Programming Resources (no B1/B2/B3, no FPGA load)"}`, false, "DAT");
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

  async function readMemory() {
    // Same synchronous lock as Start: a double click never submits twice.
    if (startLock.current || !readReadiness.ready || !ppu || siteId == null || !icpn
      || readStart == null || readSize == null) return;
    startLock.current = true;
    const abort = new AbortController();
    abortRef.current = abort;
    clearReadState();
    setReadPhase("planning");
    appendLog(`[READ] START · PPU ${ppu.alias} · ${siteLabel(siteId)} · ${icpn} · ${hex(readStart)} + ${readSize} B · independent Job, not part of the Batch`, false, "USR");
    try {
      const result = await runManagedRead({ alias: ppu.alias, siteId, icpn, address: readStart, length: readSize }, {
        onPlan: next => appendLog(`[READ] PLAN ${next.plan_id} · Route ${next.route.route_id} · Job Binding SHA256 ${next.job_binding_sha256}`, false, "DAT"),
        onRun: next => {
          setReadRun(next);
          setReadPhase(next.outcome == null ? "running" : "downloading");
        },
        onPollError: message => setReadMessage(message),
      }, abort.signal);
      const { verdict, reason } = runVerdict(result.run);
      const output = result.run.receipt?.read_output ?? null;
      let url: string | null = null;
      if (result.data) {
        url = URL.createObjectURL(new Blob([result.data.slice().buffer], { type: "application/octet-stream" }));
        readUrl.current = url;
      }
      setReadRun(result.run);
      setReadResult({ run: result.run, url, filename: output?.filename ?? null, downloadError: result.downloadError });
      appendLog(`[READ] ${verdict}${reason ? ` · ${reason}` : ""} · Run ${result.run.run_id} · Job ${result.run.receipt?.job_id ?? "—"}${
        output ? ` · ${output.bytes} B · SHA256 ${output.sha256 ?? "—"}` : ""}${result.downloadError ? ` · download: ${result.downloadError}` : ""}`,
        verdict !== "PASS" || Boolean(result.downloadError), "PPU");
      if (result.run.outcome === "OUTCOME_UNKNOWN") setUnresolved(result.run);
    } catch (reason) {
      const message = reason instanceof ManagedProgrammingBlocked ? `Not started — ${describeBlocked(reason)}`
        : reason instanceof ManagedStartOutcomeUnknown ? `OUTCOME UNKNOWN — ${reason.message} Check the PPU before reading again.`
        : reason instanceof Error ? reason.message : "Read Memory failed";
      setReadMessage(message);
      appendLog(`[READ] ${message}`, true);
    } finally {
      setReadPhase("idle");
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
      setReadRun(current => current?.run_id === next.run_id ? next : current);
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
    : operations && !needsImage
      ? "Erase only: no Programming Image is used; the Flash range of the Programming Profile is erased and proven blank."
    : source === "bundle"
      ? "Your own canonical Bundle v3. The Manager verifies it against the qualified Programming Route."
      : "Binary Programming Image (.bin). The Manager builds the canonical Bundle v3.";
  const policyNote = locale === "zh-TW"
    ? `單一 Programming Job：attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}。Repeat 固定為 1（暫不實作）。Retry／Stop Policy 需要 Manager Batch Coordinator，此版本停用。`
    : `One Programming Job: attempts = ${MANAGED_JOB_POLICY.attempts} · auto retry ${MANAGED_JOB_POLICY.auto_retry}. Repeat is fixed at 1 (not implemented). Retry / Stop Policy need the Manager Batch Coordinator and are disabled in this release.`;
  const fileDetails = file ? `${formatBytes(file.size)} · ${fileFormat(file, source)}` : null;
  const readVerdict = readRun ? runVerdict(readRun).verdict : null;
  const readOutput = readResult?.run.receipt?.read_output ?? null;
  const readStatus = readPhase === "planning" ? "PLANNING"
    : readPhase === "downloading" ? "FETCHING OUTPUT"
    : readRun && readRun.outcome == null ? runStageLabel(readRun)
    : readVerdict ? readVerdict.replace("_", " ") : readReadiness.label;
  const readProgress = readRun ? runProgressPercent(readRun) : null;
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
                checked: checkedOperations[item] && (declaredOperations.includes(item) || siteId == null),
                disabled: active || (siteId != null && !declaredOperations.includes(item)),
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
              statusClassName={`readiness-${readiness.ready ? "batch-ready" : phase !== "idle" ? "running" : "programming-unavailable"}`}
              abortLabel="ABORT"
              abortDisabled
              onAbort={() => {}}
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
            {statusNote && <div className="warning engineeringOperationWarning" role="status">{statusNote}</div>}
          </div>
        </div>

        <section className="productionProgrammingCard readMemoryCard" aria-label="Read Memory" data-testid="read-memory">
          <header><span>READ MEMORY</span><small>Independent Job · not part of the Batch · never erases, programs or reloads</small></header>
          <div className="cardBody readMemoryBody">
            <label className="workflowField">
              <span>Start Address</span>
              <input
                aria-label="Read Memory Start Address"
                value={readAddress}
                placeholder={readRoute ? hex(readRoute.flash_base) : "0x08000000"}
                disabled={active}
                onChange={event => { setReadAddress(event.target.value); clearReadState(); }}
              />
            </label>
            <label className="workflowField">
              <span>Length (bytes)</span>
              <input
                aria-label="Read Memory Length"
                value={readLength}
                placeholder={readRoute ? String(readRoute.flash_size) : "65536"}
                disabled={active}
                onChange={event => { setReadLength(event.target.value); clearReadState(); }}
              />
            </label>
            <button
              type="button"
              className="readMemoryButton"
              data-testid="read-memory-start"
              disabled={!readReadiness.ready}
              title={readReadiness.ready ? undefined : readReadiness.reason}
              onClick={() => void readMemory()}
            >READ MEMORY</button>
            <div className="readMemoryStatus" role="status" aria-label="Read Memory status" data-testid="read-memory-status"
              data-read-verdict={readVerdict ?? ""}>
              <small>READ STATUS</small>
              <b>{readStatus}{readProgress != null && readRun?.outcome == null ? ` · ${Math.round(readProgress)}%` : ""}</b>
            </div>
          </div>
          {!readReadiness.ready && !reading && phase === "idle" && readReadiness.label !== readiness.label && (
            <div className="engineeringBoundaryNote warning" role="status" data-testid="read-memory-readiness">
              <b>{readReadiness.label}</b><span>{readReadiness.reason}</span>
            </div>
          )}
          {readMessage && <div className="warning engineeringOperationWarning" role="alert" data-testid="read-memory-message">{readMessage}</div>}
          {readResult && (
            <dl className="cardBody programmingRunView" aria-label="Read Memory result" data-testid="read-memory-result">
              <dt>Result</dt><dd data-testid="read-memory-verdict">{runVerdict(readResult.run).verdict.replace("_", " ")}{runVerdict(readResult.run).reason ? ` · ${runVerdict(readResult.run).reason}` : ""}</dd>
              <dt>Range</dt><dd>{readOutput ? `${hex(readOutput.address)} + ${readOutput.bytes} B` : "—"}</dd>
              <dt>Bytes Read</dt><dd data-testid="read-memory-bytes">{readOutput && runVerdict(readResult.run).verdict === "PASS" ? readOutput.bytes : "—"}</dd>
              <dt>SHA256</dt><dd data-testid="read-memory-sha"><code>{readOutput?.sha256 ?? "—"}</code></dd>
              <dt>Job ID</dt><dd><code>{readResult.run.receipt?.job_id ?? "—"}</code></dd>
              <dt>SAFE_OFF</dt><dd>{readResult.run.receipt?.safe_off === true ? "VERIFIED" : "NOT VERIFIED"}</dd>
              <dt>Binary</dt>
              <dd>
                {readResult.url && readResult.filename
                  ? <a href={readResult.url} download={readResult.filename} data-testid="read-memory-download">Download {readResult.filename}</a>
                  : <span data-testid="read-memory-no-download">{readResult.downloadError ?? "No verified binary is available."}</span>}
              </dd>
            </dl>
          )}
        </section>

        {run && (
          <ProgrammingRunView
            run={run}
            ariaLabel="Programming run"
            executionInterface={topology?.ppus.find(item => item.alias === run.ppu_alias)
              ?.sites.find(item => item.site_id === run.site_id)?.interface ?? null}
          />
        )}
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
