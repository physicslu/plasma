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
  getProgrammingRoutes,
  getProgrammingRun,
  IMAGE_OPERATIONS,
  planProgramming,
  PROGRAMMING_OPERATIONS,
  startProgramming,
  type ImageOperation,
  type ProgrammingOperation,
  type ProgrammingPlan,
  type ProgrammingRoute,
  type ProgrammingRun,
  type ProgrammingSource,
} from "../engineering/bundle-programming-api";
import { getManagerFleet, getManagerRegistry, type ManagerRegistryPayload } from "../engineering/ppu-registry-api";
import type { FleetPPUView, FleetSiteView, FleetWebPayload } from "../fleet/fleet-contract";

export type { ProgrammingOperation, ProgrammingPlan, ProgrammingRoute, ProgrammingRun, ProgrammingSource };

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

/** Sites a committed Programming Route declares for this IC (capability, not liveness). */
export function routeSites(routes: ProgrammingRoute[] | null, icpn: string | null): number[] {
  if (!routes || !icpn) return [];
  return [...new Set(routes.filter(route => route.icpn === icpn).flatMap(route => route.sites))]
    .sort((left, right) => left - right);
}

/** Operations the Route Profile really declares for this IC on this Site, in contract order. */
export function routeOperations(
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
  siteId: number | null,
): ProgrammingOperation[] {
  if (!routes || !icpn || siteId == null) return [];
  const declared = new Set(routes
    .filter(route => route.icpn === icpn && route.sites.includes(siteId))
    .flatMap(route => route.operations));
  return PROGRAMMING_OPERATIONS.filter(operation => declared.has(operation));
}

/** Operations any committed Route declares for this IC (multi-Site selection). */
export function routeOperationsForIc(routes: ProgrammingRoute[] | null, icpn: string | null): ProgrammingOperation[] {
  if (!routes || !icpn) return [];
  const declared = new Set(routes.filter(route => route.icpn === icpn).flatMap(route => route.operations));
  return PROGRAMMING_OPERATIONS.filter(operation => declared.has(operation));
}

export const PROGRAMMING_OPERATION_LABELS: Record<ProgrammingOperation, { code: string; label: string }> = {
  flash_cycle: { code: "F", label: "Flash Cycle" },
  program: { code: "P", label: "Program" },
  verify: { code: "V", label: "Verify" },
  erase: { code: "E", label: "Erase" },
  read: { code: "R", label: "Read" },
};

export function isImageOperation(operation: string | null): operation is ImageOperation {
  return operation != null && IMAGE_OPERATIONS.has(operation);
}

export type SiteCapability = { programmable: boolean; label: string; reason: string };

/** Site capability = Route declares (IC, Site) AND the PPU reports the Site enabled and idle. */
export function siteCapability(
  site: FleetSiteView,
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
): SiteCapability {
  if (!site.enabled) return { programmable: false, label: "DISABLED", reason: "The Site is disabled on the PPU." };
  if (!icpn) return { programmable: false, label: "NO TARGET IC", reason: "Select a Target IC first." };
  if (!routeSites(routes, icpn).includes(site.site_id)) {
    return {
      programmable: false,
      label: "NO ROUTE",
      reason: `No Programming Route declares ${icpn} on Site ${site.site_id}; the Site is not qualified for it.`,
    };
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
  operation: ImageOperation;
  source: ProgrammingSource;
  file: File;
};

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

/** The single start request left the Browser but its outcome is unknown. Never resubmitted. */
export class ManagedStartOutcomeUnknown extends Error {
  constructor(readonly planId: string, message: string) {
    super(message);
    this.name = "ManagedStartOutcomeUnknown";
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

function planEchoMismatch(plan: ProgrammingPlan, request: ManagedRunRequest, sha256: string): string | null {
  if (plan.ppu_alias !== request.alias) return "PPU";
  if (plan.site_id !== request.siteId) return "Site";
  if (plan.operation !== request.operation) return "Operation";
  if (plan.route.icpn !== request.icpn) return "IC";
  if (plan.source !== request.source) return "Programming Source";
  if (plan.fpga_load !== false) return "FPGA Load";
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
  let bytes: Uint8Array;
  let sha256: string;
  try {
    bytes = new Uint8Array(await request.file.arrayBuffer());
    if (bytes.length === 0) throw new Error("the selected file is empty");
    sha256 = await sha256Hex(bytes);
  } catch (reason) {
    throw new ManagedProgrammingBlocked("lock", "file_unreadable",
      `The selected ${request.source === "bundle" ? "Bundle" : "Programming Image"} could not be read: ${errorParts(reason).message}`);
  }
  events.onLocked?.({ name: request.file.name, size: bytes.length, sha256, source: request.source });

  let plan: ProgrammingPlan;
  try {
    plan = await planProgramming(request.alias, request.source === "bundle"
      ? { icpn: request.icpn, siteId: request.siteId, operation: request.operation, bundle: bytes }
      : { icpn: request.icpn, siteId: request.siteId, operation: request.operation, image: bytes, filename: request.file.name });
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
      `The start request outcome is unknown (${message}). Nothing was resubmitted.`);
  }
  events.onRun?.(run);

  while (run.outcome == null) {
    await new Promise(resolve => setTimeout(resolve, MANAGED_POLL_MS));
    if (signal?.aborted) return run;
    try {
      run = await getProgrammingRun(request.alias, run.run_id);
      events.onRun?.(run);
    } catch (reason) {
      // Reads are safe to repeat; the run itself is never resubmitted.
      events.onPollError?.(`${errorParts(reason).message}; the run was NOT resubmitted`);
    }
  }
  return run;
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
    : receipt.expected_image_sha256 != null && receipt.readback_sha256 !== receipt.expected_image_sha256
      ? "READBACK_SHA256_MISMATCH"
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
  operation_not_in_profile: "The Programming Profile does not declare this Operation.",
  bundle_resource_not_qualified: "The Bundle's Programming Resources differ from the qualified Programming Route for this IC and Site. A Bundle declaration cannot replace hardware qualification.",
  bundle_incompatible: "The Bundle is not an admissible canonical Bundle v3 for this IC and Site.",
  programming_outcome_unknown_unresolved: "An earlier run on this PPU ended OUTCOME UNKNOWN. Reconcile and acknowledge it before programming again.",
  programming_run_in_progress: "Another programming run is in progress on this PPU.",
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
