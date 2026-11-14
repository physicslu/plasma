// Unified managed Programming (EMode Single PPU and PMode Factory Console).
//
// One formal data path for both product modes:
//   Console -> same-origin BFF -> Manager Registry / Fleet / Programming Routes
//   -> Manager programming plan + run -> PPU Runtime.
// The Browser never talks to a PPU Gateway, never builds a Bundle, never
// retries a write and never decides PASS on its own: PASS needs the Manager
// receipt with verified SAFE_OFF.

import { getManagerPpuBootstrap, sha256Hex, type ManagerBootstrapStatus } from "../engineering/ppu-bootstrap-api";
import {
  getProgrammingBatch,
  getProgrammingRoutes,
  getProgrammingRun,
  getReadOutput,
  IMAGE_OPERATIONS,
  issueBatchStart,
  planProgramming,
  SEQUENCE_OPERATIONS,
  PROGRAMMING_OPERATIONS,
  startProgramming,
  startProgrammingBatch,
  type BatchInput,
  type ImageOperation,
  type ProgrammingBatch,
  type ProgrammingBatchUnit,
  type StopPolicy,
  type ProgrammingOperation,
  type ProgrammingPlan,
  type ProgrammingRoute,
  type ProgrammingRun,
  type PlanInput,
  type ProgrammingSource,
  type SequenceOperation,
  type SingleOperation,
  type StartReconciliation,
} from "../engineering/bundle-programming-api";
import { getManagerFleet, getManagerRegistry, type ManagerRegistryPayload } from "../engineering/ppu-registry-api";
import type { FleetPPUView, FleetSiteView, FleetWebPayload } from "../fleet/fleet-contract";

export type { ProgrammingBatch, ProgrammingOperation, ProgrammingPlan, ProgrammingRoute, ProgrammingRun, ProgrammingSource, StopPolicy };

// Formal Flash Job policy (initial release). Repeat / Retry / Stop policies of
// the Mock batch runtime have no qualified execution contract here.
export const MANAGED_JOB_POLICY = Object.freeze({ attempts: 1, auto_retry: "DISABLED" as const });
export const MANAGED_POLL_MS = 1000;
export const UNASSIGNED_FACILITY = "unassigned";

export type ManagedAvailabilityCode =
  | "ready"
  | "manager-unavailable"
  | "not-commissioned"
  | "offline"
  | "stale"
  | "degraded"
  | "identity-conflict"
  | "identity-unknown"
  | "platform-unknown"
  | "unauthorized"
  | "runtime-inactive"
  | "recovery-required"
  | "routes-unavailable"
  | "outcome-unknown";

export type ManagedAvailability = {
  ready: boolean;
  code: ManagedAvailabilityCode;
  /** Short operator label, e.g. "PPU OFFLINE". */
  label: string;
  /** Exact reason shown next to a disabled Start. */
  reason: string;
};

const READY: ManagedAvailability = { ready: true, code: "ready", label: "READY", reason: "" };

function blocked(code: ManagedAvailabilityCode, label: string, reason: string): ManagedAvailability {
  return { ready: false, code, label, reason };
}

export type ManagedPpu = {
  /** Manager Registry alias: the only routing key the Browser uses. */
  alias: string;
  /** Device-reported PPU ID; never used for routing. */
  ppuId: string | null;
  facilityId: string;
  displayName: string;
  model: string | null;
  /** Gateway reachable with a current observation. Independent from Programming capability. */
  online: boolean;
  siteCount: number;
  sites: FleetSiteView[];
  /** Registry + Fleet level availability (Platform and Routes are judged separately). */
  availability: ManagedAvailability;
};

export type ManagedFacility = {
  facilityId: string;
  displayName: string;
  ppus: ManagedPpu[];
};

export type ManagedTopology = {
  facilities: ManagedFacility[];
  ppus: ManagedPpu[];
  observedAt: string | null;
};

function fleetAvailability(view: FleetPPUView | null): ManagedAvailability {
  if (!view) {
    return blocked("offline", "PPU NOT OBSERVED", "The Manager Fleet has no observation of this PPU.");
  }
  if (view.transport_state !== "reachable") {
    return blocked("offline", "PPU OFFLINE", "The Manager cannot reach this PPU Gateway.");
  }
  if (view.observation.state !== "current") {
    return blocked("stale", "PPU STALE", "The last PPU observation is stale; wait for a current observation.");
  }
  if (view.identity_conflict) {
    return blocked("identity-conflict", "PPU IDENTITY CONFLICT",
      "Another registered PPU reports the same identity; resolve it in PPU → Registration.");
  }
  if (!view.identity.ppu_id) {
    return blocked("identity-unknown", "PPU IDENTITY UNKNOWN", "The PPU did not report its PPU ID.");
  }
  if (view.execution_state !== "ready" || view.degraded) {
    return blocked("degraded", "PPU DEGRADED", "The PPU Runtime is not ready for execution.");
  }
  return READY;
}

/**
 * Programming topology from the formal Manager Registry and Fleet only.
 * Only commissioned Registry entries are offered for Programming; pending or
 * disabled entries stay a PPU → Registration concern.
 */
export function buildManagedTopology(
  registry: ManagerRegistryPayload,
  fleet: FleetWebPayload | null,
): ManagedTopology {
  const views = new Map<string, FleetPPUView>();
  for (const view of fleet?.ppus ?? []) if (view.alias) views.set(view.alias, view);
  const ppus: ManagedPpu[] = [];
  for (const entry of registry.ppus) {
    if (!entry.alias || entry.lifecycle !== "commissioned") continue;
    const view = views.get(entry.alias) ?? null;
    ppus.push({
      alias: entry.alias,
      ppuId: view?.identity.ppu_id ?? null,
      facilityId: view?.identity.facility_id ?? UNASSIGNED_FACILITY,
      displayName: view?.identity.display_name ?? entry.alias,
      model: view?.identity.model ?? null,
      online: view?.transport_state === "reachable" && view.observation.state === "current",
      siteCount: view?.topology.site_count ?? 0,
      sites: view?.topology.sites ?? [],
      availability: fleet ? fleetAvailability(view)
        : blocked("manager-unavailable", "FLEET UNAVAILABLE", "The Manager Fleet observation is unavailable."),
    });
  }
  const facilities = new Map<string, ManagedFacility>();
  for (const ppu of ppus) {
    const facility = facilities.get(ppu.facilityId)
      ?? { facilityId: ppu.facilityId, displayName: ppu.facilityId, ppus: [] };
    facility.ppus.push(ppu);
    facilities.set(ppu.facilityId, facility);
  }
  return { facilities: [...facilities.values()], ppus, observedAt: fleet?.observed_at ?? null };
}

export async function loadManagedTopology(): Promise<ManagedTopology> {
  const [registry, fleet] = await Promise.all([
    getManagerRegistry(),
    getManagerFleet().catch(() => null),
  ]);
  return buildManagedTopology(registry, fleet);
}

/**
 * Platform admission as the Manager itself will judge it at plan time. This
 * only reads; it never enrolls, rotates a credential or raises a generation.
 */
export function platformAvailability(status: ManagerBootstrapStatus | null, error: string | null): ManagedAvailability {
  if (error || !status) {
    return blocked("platform-unknown", "PLATFORM UNKNOWN",
      error ?? "The PPU Platform (Bootstrap) status has not been read yet.");
  }
  if (status.pairing.paired !== true || status.pairing.device_match !== true) {
    return blocked("unauthorized", "NOT AUTHORIZED",
      "This Manager holds no valid Controller credential for this PPU. Complete Local Owner Enrollment in "
      + "PPU → Platform; nothing is enrolled or rotated automatically.");
  }
  if (status.bootstrap.runtime.state !== "runtime_active") {
    return blocked("runtime-inactive", "RUNTIME NOT ACTIVE",
      `The PPU Runtime is ${status.bootstrap.runtime.state}; deploy or start it in PPU → Platform.`);
  }
  if (status.bootstrap.deployment?.state === "recovery_required") {
    return blocked("recovery-required", "RECOVERY REQUIRED",
      "The PPU requires explicit recovery in PPU → Platform before any Programming.");
  }
  return READY;
}

export async function loadPlatformAvailability(alias: string): Promise<ManagedAvailability> {
  try {
    return platformAvailability(await getManagerPpuBootstrap(alias), null);
  } catch (reason) {
    return platformAvailability(null, reason instanceof Error ? reason.message : "PPU Platform status unavailable");
  }
}

export type RoutesState = { routes: ProgrammingRoute[] | null; error: string | null };

export async function loadProgrammingRoutes(alias: string): Promise<RoutesState> {
  try {
    return { routes: await getProgrammingRoutes(alias), error: null };
  } catch (reason) {
    return { routes: null, error: reason instanceof Error ? reason.message : "Programming Routes unavailable" };
  }
}

export function routesAvailability(state: RoutesState | null): ManagedAvailability {
  if (!state) return blocked("routes-unavailable", "ROUTES LOADING", "Programming Routes are loading.");
  if (state.error || !state.routes) {
    return blocked("routes-unavailable", "ROUTES UNAVAILABLE", state.error ?? "Programming Routes are unavailable.");
  }
  return READY;
}

/** ICPN capability is profile-owned; physical Site inventory is PPU-owned. */
export function routeSupportsIc(routes: ProgrammingRoute[] | null, icpn: string | null): boolean {
  return Boolean(routes && icpn && routes.some(route => route.icpn === icpn));
}

/** Operations are declared by the IC Profile, never by a physical Site number. */
export function routeOperations(
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
  siteId: number | null,
): SingleOperation[] {
  if (!routes || !icpn || siteId == null) return [];
  const declared = new Set(routes
    .filter(route => route.icpn === icpn)
    .flatMap(route => route.operations));
  return PROGRAMMING_OPERATIONS.filter(operation => declared.has(operation));
}

/** Operations any committed Route declares for this IC (multi-Site selection). */
export function routeOperationsForIc(routes: ProgrammingRoute[] | null, icpn: string | null): SingleOperation[] {
  if (!routes || !icpn) return [];
  const declared = new Set(routes.filter(route => route.icpn === icpn).flatMap(route => route.operations));
  return PROGRAMMING_OPERATIONS.filter(operation => declared.has(operation));
}

export const PROGRAMMING_OPERATION_LABELS: Record<
  SingleOperation | "erase" | "program" | "verify",
  { code: string; label: string }
> = {
  flash_cycle: { code: "F", label: "Flash Cycle" },
  program: { code: "P", label: "Program" },
  verify: { code: "V", label: "Verify" },
  erase: { code: "E", label: "Erase" },
  read: { code: "R", label: "Read" },
};

/** E / P / V steps declared by the IC Profile, independent of Site (fixed order). */
export function routeSequenceOperations(
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
  siteId: number | null,
): SequenceOperation[] {
  if (!routes || !icpn || siteId == null) return [];
  const declared = new Set(routes
    .filter(route => route.icpn === icpn)
    .flatMap(route => route.operations));
  return SEQUENCE_OPERATIONS.filter(operation => declared.has(operation));
}

/** The IC/operation Profile chosen by Manager; Site readiness is a separate PPU check. */
export function routeDeclaring(
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
  siteId: number | null,
  operations: readonly string[],
): ProgrammingRoute | null {
  if (!routes || !icpn || siteId == null || !operations.length) return null;
  const matches = routes.filter(route => route.icpn === icpn
    && operations.every(operation => route.operations.includes(operation)));
  return matches.length === 1 ? matches[0] : null;
}

export function isImageOperation(operation: string | null): operation is ImageOperation {
  return operation != null && IMAGE_OPERATIONS.has(operation);
}

export type SiteCapability = { programmable: boolean; label: string; reason: string };

/** Capability = an IC Profile exists AND the PPU reports a real, idle Site. */
export function siteCapability(
  site: FleetSiteView,
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
): SiteCapability {
  if (!site.enabled) return { programmable: false, label: "DISABLED", reason: "The Site is disabled on the PPU." };
  if (!icpn) return { programmable: false, label: "NO TARGET IC", reason: "Select a Target IC first." };
  if (!routeSupportsIc(routes, icpn)) {
    return {
      programmable: false,
      label: "NO PROFILE",
      reason: `No Programming Profile declares ${icpn}.`,
    };
  }
  if (site.interface !== "openocd" && site.interface !== "fpga") {
    return { programmable: false, label: "INTERFACE UNAVAILABLE",
      reason: "The PPU has not activated a compatible real programming interface on this Site." };
  }
  if (site.current_job_id || site.state !== "idle") {
    return { programmable: false, label: site.state.toUpperCase(), reason: "The Site is busy or not idle." };
  }
  return { programmable: true, label: "READY", reason: "" };
}

// ------------------------------------------------------------------ execution

export type ManagedRunRequest = {
  alias: string;
  siteId: number;
  icpn: string;
  source: ProgrammingSource;
} & (
  // One programming Job with an ordered E / P / V list and its Image or Bundle.
  | { operations: readonly SequenceOperation[]; operation?: undefined; file: File }
  // An erase-only list: no Image, an explicit erase range.
  | { operations: readonly ["erase"]; operation?: undefined; file: null; range: { address: number; length: number } }
  // Legacy complete cycle (PMode).
  | { operation: ImageOperation; operations?: undefined; file: File }
);

export type LockedInput = { name: string; size: number; sha256: string; source: ProgrammingSource };

export type ManagedRunEvents = {
  onLocked?: (input: LockedInput) => void;
  onPlan?: (plan: ProgrammingPlan) => void;
  onRun?: (run: ProgrammingRun) => void;
  onPollError?: (message: string) => void;
};

/** The Manager refused before any Job existed. Nothing was submitted. */
export class ManagedProgrammingBlocked extends Error {
  constructor(readonly stage: "lock" | "plan" | "start", readonly code: string | null, message: string) {
    super(message);
    this.name = "ManagedProgrammingBlocked";
  }
}

/** What a lost Start was for: enough to reconcile it with the Manager later. */
export type StartIdentity = {
  /** Manager-issued: the run's plan ID, or the Batch start ID. */
  startId: string;
  kind: "run" | "batch";
  /** One Site for a run; every Site the Batch covers on this PPU. */
  siteIds: readonly number[];
  operation: string;
  /** Known for a run (from its plan); a Batch plans inside the Manager. */
  jobBindingSha256: string | null;
};

/** The single start request left the Browser but its outcome is unknown. Never resubmitted. */
export class ManagedStartOutcomeUnknown extends Error {
  constructor(readonly planId: string, message: string, readonly identity: StartIdentity | null = null) {
    super(message);
    this.name = "ManagedStartOutcomeUnknown";
  }
}

export type StartHoldIdentity = {
  alias: string; siteIds: readonly number[]; kind: "READ" | "PROGRAMMING";
  startId: string | null; jobBindingSha256: string | null;
};

export type StartReconciliationDecision =
  /** The hold may be released (the operator's click is the acknowledgement). */
  | { action: "RELEASE"; summary: string }
  /** The Manager run is OUTCOME UNKNOWN: its own acknowledge comes first. */
  | { action: "ACKNOWLEDGE_RUN"; runId: string; summary: string }
  /** Never admitted so far, but a delayed request still could be: void it. */
  | { action: "VOID"; summary: string }
  | { action: "BLOCKED"; summary: string };

/**
 * What the Manager's reconciliation allows for one held Start. Pure.
 *
 * The answer must be about THIS start on THIS PPU, Site and Job Binding;
 * anything else, and anything the Manager cannot prove, keeps the hold.
 */
/**
 * The Sites this start is on record for, ascending, or null when the Manager
 * has none yet. A Batch records its whole Target Set; a run records one Site.
 */
function recordedSites(
  identity: NonNullable<StartReconciliation["identity"]>, alias: string,
): number[] | null {
  const targets = identity.targets;
  if (targets != null) {
    const mine = targets.filter(target => target.ppu_alias === alias);
    if (mine.length === 0) return [];
    return mine.flatMap(target => [...target.site_ids]).sort((left, right) => left - right);
  }
  return identity.site_id == null ? null : [identity.site_id];
}

export function decideStartReconciliation(
  hold: StartHoldIdentity, answer: StartReconciliation,
): StartReconciliationDecision {
  const blocked = (summary: string): StartReconciliationDecision => ({ action: "BLOCKED", summary });
  if (!hold.startId) return blocked("this hold has no Manager start ID to reconcile");
  if (answer.schema !== "plasma.manager.programming-start-reconciliation.v1" || answer.read_only !== true) {
    return blocked("the Manager answer is not a Start reconciliation");
  }
  // A Batch start names no PPU until a Target Set is admitted with it, so a
  // missing alias is not a mismatch; a DIFFERENT alias still is.
  if (answer.start_id !== hold.startId
    || (answer.ppu_alias != null && answer.ppu_alias !== hold.alias)) {
    return blocked("the Manager answered for another start or PPU");
  }
  const identity = answer.identity;
  if (identity) {
    const wantedKind = hold.kind === "READ" ? "run" : "batch";
    const wantedSites = [...hold.siteIds].sort((left, right) => left - right);
    const recorded = recordedSites(identity, hold.alias);
    const sitesKnown = recorded !== null;
    if (answer.kind !== wantedKind
      || (identity.ppu_alias != null && identity.ppu_alias !== hold.alias)
      || (identity.ppu_alias == null && wantedKind !== "batch")
      || (sitesKnown && JSON.stringify(recorded) !== JSON.stringify(wantedSites))
      // Only a Batch that was never admitted has no Site on record yet.
      || (!sitesKnown && !(wantedKind === "batch" && (answer.state === "ACCEPTANCE_PENDING" || answer.state === "NOT_ACCEPTED")))
      || (hold.kind === "READ" && identity.operation !== "read")
      || (hold.kind === "PROGRAMMING" && identity.operation !== "programming")
      || (hold.jobBindingSha256 != null && identity.job_binding_sha256 !== hold.jobBindingSha256)) {
      return blocked("the Manager record does not match this PPU, Site, Operation or Job Binding");
    }
  } else if (answer.state !== "OUTCOME_UNKNOWN") {
    return blocked("the Manager answer carries no identity");
  }
  const reason = answer.reason ?? "no reason reported";
  switch (answer.state) {
    case "NOT_ACCEPTED":
      return { action: "RELEASE", summary: `the Manager proves the Start was never admitted (${reason}); no Job was submitted` };
    case "ACCEPTANCE_PENDING":
      return { action: "VOID", summary: `the Manager has not admitted this Start, but a delayed request still could be for ${answer.expires_in_s ?? "?"} s` };
    case "ACCEPTED_RUNNING":
      return blocked(`the Manager admitted this Start and it is still running (${answer.run?.run_id ?? answer.batch?.batch_id ?? "?"})`);
    case "TERMINAL_CONFIRMED": {
      const id = answer.run ? `Run ${answer.run.run_id}` : answer.batch ? `Batch ${answer.batch.batch_id}` : null;
      if (!id || !answer.outcome || answer.outcome === "OUTCOME_UNKNOWN") return blocked("the Manager reports no definite result");
      return { action: "RELEASE", summary: `the Manager admitted this Start as ${id} and it ended ${answer.outcome}${answer.reason ? ` (${answer.reason})` : ""}` };
    }
    case "OUTCOME_UNKNOWN":
      if (answer.unknown_run_id && answer.acknowledged === false) {
        return { action: "ACKNOWLEDGE_RUN", runId: answer.unknown_run_id,
          summary: `the Manager admitted this Start; Run ${answer.unknown_run_id} ended OUTCOME UNKNOWN (${reason}) and is not acknowledged` };
      }
      if (answer.unknown_run_id && answer.acknowledged === true) {
        return { action: "RELEASE", summary: `Run ${answer.unknown_run_id} ended OUTCOME UNKNOWN and its reconciliation is acknowledged on the Manager` };
      }
      return blocked(`the Manager cannot prove what became of this Start (${reason})`);
    default:
      return blocked("the Manager reported an unrecognized reconciliation state");
  }
}

function errorParts(reason: unknown): { status: number | null; code: string | null; message: string } {
  const record = reason as { status?: unknown; code?: unknown; message?: unknown } | null;
  return {
    status: typeof record?.status === "number" ? record.status : null,
    code: typeof record?.code === "string" ? record.code : null,
    message: typeof record?.message === "string" && record.message ? record.message : "request failed",
  };
}

function planEchoMismatch(plan: ProgrammingPlan, request: ManagedRunRequest, sha256: string | null): string | null {
  if (plan.ppu_alias !== request.alias) return "PPU";
  if (plan.site_id !== request.siteId) return "Site";
  if (request.operations) {
    // Exactly the selected list, as one programming Job; never another Operation.
    if (plan.operation !== "programming"
      || JSON.stringify(plan.operations) !== JSON.stringify(request.operations)
      || JSON.stringify(plan.job_binding.operations) !== JSON.stringify(request.operations)) return "Operations";
  } else if (plan.operation !== request.operation || plan.operations != null) {
    return "Operation";
  }
  if (plan.route.icpn !== request.icpn) return "IC";
  if (plan.fpga_load !== false) return "FPGA Load";
  if (request.file === null) {
    const range = plan.job_binding.range;
    return plan.source === "range" && plan.image_asset == null
      && range.address === request.range.address && range.length === request.range.length ? null : "Erase range";
  }
  if (plan.source !== request.source) return "Programming Source";
  const lockedSha = request.source === "bundle" ? plan.bundle?.archive_sha256 : plan.image_asset?.sha256;
  if (lockedSha !== sha256) return request.source === "bundle" ? "Bundle SHA256" : "Programming Image SHA256";
  return null;
}

/**
 * One Start: lock -> plan -> exactly one start -> observe the Manager run.
 *
 * The Backend plan is never skipped; only the manual Prepare step is gone.
 * A plan is consumed by its single start; neither a lost start response nor
 * OUTCOME_UNKNOWN is ever followed by another write. Status reads repeat.
 */
export async function runManagedProgramming(
  request: ManagedRunRequest,
  events: ManagedRunEvents = {},
  signal?: AbortSignal,
): Promise<ProgrammingRun> {
  let bytes: Uint8Array | null = null;
  let sha256: string | null = null;
  if (request.file !== null) {
    try {
      bytes = new Uint8Array(await request.file.arrayBuffer());
      if (bytes.length === 0) throw new Error("the selected file is empty");
      sha256 = await sha256Hex(bytes);
    } catch (reason) {
      throw new ManagedProgrammingBlocked("lock", "file_unreadable",
        `The selected ${request.source === "bundle" ? "Bundle" : "Programming Image"} could not be read: ${errorParts(reason).message}`);
    }
    events.onLocked?.({ name: request.file.name, size: bytes.length, sha256, source: request.source });
  }

  const target = { icpn: request.icpn, siteId: request.siteId };
  const selector = request.operations
    ? { operations: request.operations } : { operation: request.operation };
  const input: PlanInput = request.file === null
    ? { ...target, operations: ["erase"], ...request.range }
    : request.source === "bundle"
      ? { ...target, ...selector, bundle: bytes! }
      : { ...target, ...selector, image: bytes!, filename: request.file.name };
  let plan: ProgrammingPlan;
  try {
    plan = await planProgramming(request.alias, input);
  } catch (reason) {
    const { code, message } = errorParts(reason);
    throw new ManagedProgrammingBlocked("plan", code, message);
  }
  const mismatch = planEchoMismatch(plan, request, sha256);
  if (mismatch) {
    throw new ManagedProgrammingBlocked("plan", "plan_echo_mismatch",
      `The Manager plan does not match the locked ${mismatch}; nothing was started.`);
  }
  events.onPlan?.(plan);

  let run: ProgrammingRun;
  try {
    run = await startProgramming(request.alias, plan.plan_id);
  } catch (reason) {
    const { status, code, message } = errorParts(reason);
    // A 4xx is a definite refusal. Anything else may have reached the Manager.
    if (status != null && status >= 400 && status < 500) {
      throw new ManagedProgrammingBlocked("start", code, message);
    }
    throw new ManagedStartOutcomeUnknown(plan.plan_id,
      `The start request outcome is unknown (${message}). Nothing was resubmitted.`,
      { startId: plan.plan_id, kind: "run", siteIds: [plan.site_id], operation: plan.operation,
        jobBindingSha256: plan.job_binding_sha256 });
  }
  events.onRun?.(run);
  return observeRun(request.alias, run, events, signal);
}

async function observeRun(
  alias: string,
  started: ProgrammingRun,
  events: ManagedRunEvents,
  signal?: AbortSignal,
): Promise<ProgrammingRun> {
  let run = started;
  while (run.outcome == null) {
    await new Promise(resolve => setTimeout(resolve, MANAGED_POLL_MS));
    if (signal?.aborted) return run;
    try {
      run = await getProgrammingRun(alias, run.run_id);
      events.onRun?.(run);
    } catch (reason) {
      // Reads are safe to repeat; the run itself is never resubmitted.
      events.onPollError?.(`${errorParts(reason).message}; the run was NOT resubmitted`);
    }
  }
  return run;
}

export type ManagedReadRequest = { alias: string; siteId: number; icpn: string; address: number; length: number };
export type ManagedReadResult = {
  run: ProgrammingRun;
  /** The verified bytes; null unless the run is PASS and the download re-hashed correctly. */
  data: Uint8Array | null;
  /** Why a PASS run has no usable download. */
  downloadError: string | null;
};

/**
 * Read Memory: an independent Job (never part of a Batch, never counted in
 * PASS / FAIL / Yield). Plan -> exactly one start -> observe -> fetch the
 * binary through the Manager and re-hash it against the receipt.
 */
export async function runManagedRead(
  request: ManagedReadRequest,
  events: ManagedRunEvents = {},
  signal?: AbortSignal,
): Promise<ManagedReadResult> {
  let plan: ProgrammingPlan;
  try {
    plan = await planProgramming(request.alias, {
      icpn: request.icpn, siteId: request.siteId, operation: "read",
      address: request.address, length: request.length,
    });
  } catch (reason) {
    const { code, message } = errorParts(reason);
    throw new ManagedProgrammingBlocked("plan", code, message);
  }
  const range = plan.job_binding.range;
  if (plan.ppu_alias !== request.alias || plan.site_id !== request.siteId || plan.operation !== "read"
    || plan.operations != null || plan.source !== "range" || plan.image_asset != null
    || plan.activation_required !== false || plan.fpga_load !== false
    || plan.route.icpn !== request.icpn
    || range.address !== request.address || range.length !== request.length) {
    throw new ManagedProgrammingBlocked("plan", "plan_echo_mismatch",
      "The Manager plan is not exactly this Read Memory request; nothing was started.");
  }
  events.onPlan?.(plan);
  let run: ProgrammingRun;
  try {
    run = await startProgramming(request.alias, plan.plan_id);
  } catch (reason) {
    const { status, code, message } = errorParts(reason);
    if (status != null && status >= 400 && status < 500) {
      throw new ManagedProgrammingBlocked("start", code, message);
    }
    throw new ManagedStartOutcomeUnknown(plan.plan_id,
      `The Read Memory start outcome is unknown (${message}). Nothing was resubmitted.`,
      { startId: plan.plan_id, kind: "run", siteIds: [plan.site_id], operation: "read",
        jobBindingSha256: plan.job_binding_sha256 });
  }
  events.onRun?.(run);
  run = await observeRun(request.alias, run, events, signal);
  if (runVerdict(run).verdict !== "PASS") return { run, data: null, downloadError: null };
  const output = run.receipt?.read_output;
  try {
    const data = await getReadOutput(request.alias, run.run_id);
    if (!output || data.length !== output.bytes || await sha256Hex(data) !== output.sha256) {
      return { run, data: null, downloadError: "The downloaded bytes do not match the receipt SHA256." };
    }
    return { run, data, downloadError: null };
  } catch (reason) {
    return { run, data: null, downloadError: errorParts(reason).message };
  }
}

/** Distributes over the request union, so narrowing by `file` still works. */
type WithoutSite<T> = T extends unknown ? Omit<T, "siteId"> : never;

export type ManagedBatchRequest =
  WithoutSite<Extract<ManagedRunRequest, { operations: readonly SequenceOperation[] }>>
  & { siteIds: readonly number[]; retryLimit: number; stopPolicy: StopPolicy };

export type ManagedBatchEvents = {
  onLocked?: (input: LockedInput) => void;
  onBatch?: (batch: ProgrammingBatch) => void;
  onPollError?: (message: string) => void;
};

/**
 * EMode Start: lock -> exactly one Batch request -> observe. The Manager
 * plans every attempt, submits each Job once and alone decides, by its Retry
 * and Stop Policy contract, whether another attempt follows. The Browser
 * never retries anything: a lost Batch response is OUTCOME UNKNOWN.
 */
export async function runManagedBatch(
  request: ManagedBatchRequest,
  events: ManagedBatchEvents = {},
  signal?: AbortSignal,
): Promise<ProgrammingBatch> {
  let bytes: Uint8Array | null = null;
  if (request.file !== null) {
    try {
      bytes = new Uint8Array(await request.file.arrayBuffer());
      if (bytes.length === 0) throw new Error("the selected file is empty");
      events.onLocked?.({ name: request.file.name, size: bytes.length, sha256: await sha256Hex(bytes), source: request.source });
    } catch (reason) {
      throw new ManagedProgrammingBlocked("lock", "file_unreadable",
        `The selected ${request.source === "bundle" ? "Bundle" : "Programming Image"} could not be read: ${errorParts(reason).message}`);
    }
  }
  const common = {
    icpn: request.icpn, alias: request.alias, siteIds: [...request.siteIds],
    retryLimit: request.retryLimit, stopPolicy: request.stopPolicy,
  };
  const input: BatchInput = request.file === null
    ? { ...common, operations: ["erase"], ...request.range }
    : request.source === "bundle"
      ? { ...common, operations: request.operations, bundle: bytes! }
      : { ...common, operations: request.operations, image: bytes!, filename: request.file.name };
  // The Manager issues the start ID first, so a lost Batch answer can be
  // reconciled. Issuing it submits nothing: a failure here is a refusal.
  let startId: string;
  try {
    startId = await issueBatchStart(request.alias);
    if (!/^[0-9a-f]{32}$/.test(startId)) throw new Error("the Manager issued no start ID");
  } catch (reason) {
    const { code, message } = errorParts(reason);
    throw new ManagedProgrammingBlocked("plan", code,
      `The Manager did not issue a start ID (${message}); nothing was started.`);
  }
  let batch: ProgrammingBatch;
  try {
    batch = await startProgrammingBatch(input, startId);
  } catch (reason) {
    const { status, code, message } = errorParts(reason);
    // A 4xx is a definite refusal: no Batch exists and no Job was submitted.
    if (status != null && status >= 400 && status < 500) {
      throw new ManagedProgrammingBlocked("plan", code, message);
    }
    throw new ManagedStartOutcomeUnknown(startId,
      `The Batch request outcome is unknown (${message}). Nothing was resubmitted.`,
      { startId, kind: "batch", siteIds: [...request.siteIds],
        operation: "programming", jobBindingSha256: null });
  }
  events.onBatch?.(batch);
  while (batch.outcome == null) {
    await new Promise(resolve => setTimeout(resolve, MANAGED_POLL_MS));
    if (signal?.aborted) return batch;
    try {
      batch = await getProgrammingBatch(batch.batch_id);
      events.onBatch?.(batch);
    } catch (reason) {
      events.onPollError?.(`${errorParts(reason).message}; nothing was resubmitted`);
    }
  }
  return batch;
}

export type BatchVerdict = RunVerdict | "PARTIAL" | "STOPPED";

/**
 * One Site's verdict.
 *
 * PASS needs that Site's own Manager outcome AND the evidence the Manager
 * publishes for its last attempt: a PASS attempt, SAFE_OFF verified and a
 * confirmed Job Binding. The Batch is sequential, so the Browser holds the
 * full run receipt of one Site at a time; when it holds THIS Site's run, the
 * receipt must pass `runVerdict` for exactly the requested list on exactly
 * this PPU and Site as well. A Site that has moved out of the current run is
 * judged on the Manager's record of it - never downgraded for being past.
 */
export function batchSiteVerdict(
  batch: ProgrammingBatch, unit: ProgrammingBatchUnit, run: ProgrammingRun | null,
): { verdict: BatchVerdict; reason: string | null } {
  if (unit.outcome == null) return { verdict: "RUNNING", reason: null };
  if (unit.outcome !== "PASS") return { verdict: unit.outcome, reason: unit.reason };
  const attempt = unit.attempts[unit.attempts.length - 1];
  if (!attempt) return { verdict: "FAIL", reason: "ATTEMPT_RECORD_MISSING" };
  const key = attempt.job_key;
  const failed = attempt.outcome !== "PASS" ? "LAST_ATTEMPT_NOT_PASS"
    // Site identity: the attempt must be the Manager's record of THIS Site of
    // THIS PPU in THIS Batch, never another Site's evidence read across.
    : key == null || key.ppu_alias !== unit.ppu_alias || key.site_id !== unit.site_id
      || key.batch_id !== batch.batch_id ? "ATTEMPT_IDENTITY_MISMATCH"
    : attempt.safe_off !== true ? "SAFE_OFF_NOT_VERIFIED"
    : !attempt.job_binding_sha256 ? "JOB_BINDING_MISSING"
    : !attempt.run_id ? "RUN_ID_MISSING"
    : null;
  if (failed) return { verdict: "FAIL", reason: failed };
  if (run) {
    const judged = runVerdict(run);
    if (judged.verdict !== "PASS") return { verdict: "FAIL", reason: judged.reason ?? "LAST_RUN_NOT_PASS" };
    if (run.ppu_alias !== unit.ppu_alias || run.site_id !== unit.site_id
      || JSON.stringify(run.receipt?.operations) !== JSON.stringify(batch.operations)) {
      return { verdict: "FAIL", reason: "RUN_DOES_NOT_MATCH_BATCH" };
    }
  }
  return { verdict: "PASS", reason: null };
}

/**
 * Batch verdict, derived from the Sites and never instead of them.
 *
 * The Manager's aggregate is necessary but not sufficient: a PASS also needs
 * EVERY Site to pass `batchSiteVerdict`, and the Browser only ever holds the
 * run of the latest attempt, so a Site whose run it cannot see is not proven.
 * Worst wins, in the Manager's own priority order.
 */
export function batchVerdict(batch: ProgrammingBatch): { verdict: BatchVerdict; reason: string | null } {
  if (batch.outcome == null) return { verdict: "RUNNING", reason: null };
  if (batch.outcome !== "PASS" && batch.outcome !== "PARTIAL") {
    return { verdict: batch.outcome, reason: batch.reason };
  }
  const order: BatchVerdict[] = ["OUTCOME_UNKNOWN", "FAIL", "BLOCKED", "PARTIAL", "RUNNING", "PASS"];
  let worst: { verdict: BatchVerdict; reason: string | null } = { verdict: "PASS", reason: null };
  for (const unit of batch.units) {
    const judged = batchSiteVerdict(batch, unit, runOfUnit(batch, unit));
    if (order.indexOf(judged.verdict) < order.indexOf(worst.verdict)) worst = judged;
  }
  if (batch.outcome === "PARTIAL" && worst.verdict === "PASS") {
    return { verdict: "PARTIAL", reason: batch.reason };
  }
  return worst;
}

/**
 * The run the Browser holds for one Site, or none.
 *
 * It is the run of THAT Site's last attempt, matched by run_id: the Batch
 * carries one run record at a time, so another Site's run is never read as
 * this Site's evidence.
 */
export function runOfUnit(batch: ProgrammingBatch, unit: ProgrammingBatchUnit): ProgrammingRun | null {
  const run = batch.current_run;
  const attempt = unit.attempts[unit.attempts.length - 1];
  if (!run || !attempt || attempt.run_id == null || run.run_id !== attempt.run_id) return null;
  return run.ppu_alias === unit.ppu_alias && run.site_id === unit.site_id ? run : null;
}

export type RunVerdict = "RUNNING" | "PASS" | "FAIL" | "BLOCKED" | "OUTCOME_UNKNOWN";

/**
 * UI verdict. PASS needs the Manager outcome AND a receipt that proves a single
 * submission, verified SAFE_OFF, the bound Job Binding / Resources and, when an
 * Image was written, a matching readback. Anything short of that is not PASS.
 */
export function runVerdict(run: ProgrammingRun): { verdict: RunVerdict; reason: string | null } {
  if (run.outcome == null) return { verdict: "RUNNING", reason: null };
  if (run.outcome !== "PASS") return { verdict: run.outcome, reason: run.reason };
  const receipt = run.receipt;
  const failed = !receipt ? "RECEIPT_MISSING"
    : receipt.safe_off !== true ? "SAFE_OFF_NOT_VERIFIED"
    : run.job_submission_count !== 1 ? "JOB_SUBMISSION_COUNT_NOT_ONE"
    : run.auto_retry !== "DISABLED" ? "AUTO_RETRY_NOT_DISABLED"
    : !receipt.job_id ? "JOB_ID_MISSING"
    : receipt.observed_job_binding_sha256 !== receipt.expected_job_binding_sha256 ? "JOB_BINDING_NOT_CONFIRMED"
    : receipt.observed_resource_set_sha256 !== receipt.expected_resource_set_sha256 ? "RESOURCE_SET_NOT_CONFIRMED"
    // A readback is owed only when the Job verifies: the legacy cycle or a list with Verify.
    : (receipt.operation === "flash_cycle" || receipt.operations?.includes("verify"))
      && (receipt.expected_image_sha256 == null || receipt.readback_sha256 !== receipt.expected_image_sha256)
      ? "READBACK_SHA256_MISMATCH"
    : receipt.operation === "programming"
      && JSON.stringify(receipt.observed_operations) !== JSON.stringify(receipt.operations)
      ? "OPERATIONS_NOT_CONFIRMED"
    : receipt.operation === "read" && receipt.read_output?.available !== true
      ? "READ_OUTPUT_UNAVAILABLE"
    : null;
  return failed ? { verdict: "FAIL", reason: failed } : { verdict: "PASS", reason: null };
}

/** Real Manager / PPU progress only; null when the PPU has not reported any. */
export function runProgressPercent(run: ProgrammingRun): number | null {
  const value = run.job?.progress_percent;
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
}

export function runStageLabel(run: ProgrammingRun): string {
  if (run.outcome != null) return run.outcome.replace("_", " ");
  const last = run.steps[run.steps.length - 1];
  if (run.job?.stage) return String(run.job.stage).toUpperCase();
  return (last?.step ?? run.state).toUpperCase();
}

const BLOCK_GUIDANCE: Record<string, string> = {
  ppu_not_enabled: "The PPU is not commissioned; complete Validate & Enable in PPU → Registration.",
  bootstrap_pairing_required: "This Manager holds no valid Controller credential for this PPU (PPU → Platform → Local Owner Enrollment).",
  ppu_runtime_not_active: "The PPU Runtime is not active.",
  ppu_recovery_required: "The PPU Active Asset Set requires explicit recovery (PPU → Platform).",
  programming_route_not_found: "No Programming Route declares this IC on this Site.",
  operation_not_in_profile: "No Programming Profile for this IC and Site declares the selected Operations.",
  operations_invalid: "The selected Operations are not a supported combination.",
  resource_activation_requires_image: "The PPU does not hold these Programming Resources yet. Run a Job with a Programming Image (Program) first; an Erase-only or Read Job cannot activate Resources.",
  job_binding_invalid: "The address range is outside the Flash range of the Programming Profile.",
  bundle_resource_not_qualified: "The Bundle's Programming Resources differ from the qualified Programming Route for this IC and Site. A Bundle declaration cannot replace hardware qualification.",
  bundle_incompatible: "The Bundle is not an admissible canonical Bundle v3 for this IC and Site.",
  programming_outcome_unknown_unresolved: "An earlier run on this PPU ended OUTCOME UNKNOWN. Reconcile and acknowledge it before programming again.",
  programming_run_in_progress: "Another programming run is in progress on this PPU.",
  programming_batch_in_progress: "Another programming Batch is in progress on this PPU.",
  repeat_not_supported: "Repeat is not implemented; it stays 1.",
  ppu_resource_identity_unknown: "The PPU Resource identity could not be read; nothing was changed.",
  ppu_runtime_resource_identity_unsupported: "The PPU Runtime does not report a verified Resource identity.",
  maintenance_authorization_required: "This Control Station session is not authorized for PPU writes.",
};

/** Exact, operator-facing reason for a refused plan or start; keeps the Manager detail. */
export function describeBlocked(error: ManagedProgrammingBlocked): string {
  const guidance = error.code ? BLOCK_GUIDANCE[error.code] : undefined;
  const code = error.code ? `${error.code}: ` : "";
  return guidance ? `${code}${guidance} (${error.message})` : `${code}${error.message}`;
}
