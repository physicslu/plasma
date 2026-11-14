import { BootstrapApiError } from "./ppu-bootstrap-api";

// Console-driven Bundle programming (owner Gate 1, 2026-11-09; OFE-1B).
// Browser -> same-origin BFF -> Manager. The Manager resolves the
// Programming Route, compares the Resource Set the PPU itself derived from
// its Active Set, runs B1/B2/B3 only when the Resources differ and submits
// exactly one Job with the user-selected Operation and its Job Binding.
// The Browser never builds or signs a Bundle and never talks to the PPU.

export const PROGRAMMING_CONFIRM_TOKEN = "PROGRAM";
export const PROGRAMMING_ACK_TOKEN = "OUTCOME_UNKNOWN_RECONCILED";

export type ProgrammingRoute = {
  route_id: string;
  target: { platform: string; board: string; fpga_part: string };
  icpn: string;
  site_interface: string;
  provider: string;
  profile: string;
  operations: string[];
  driver_abi: string;
  transport: string;
  max_image_bytes: number;
  target_config: string;
  flash_base: number;
  flash_size: number;
};

// The formal execution model is ONE programming Job that runs an ordered
// `operations` list drawn from erase -> program -> verify: every legal E/P/V
// selection (all three included) is that one Job with one Job ID, one Site
// lease, one Job Binding and one receipt. A Route Profile declares the basic
// operations it supports.
export const SEQUENCE_OPERATIONS = ["erase", "program", "verify"] as const;
export type SequenceOperation = typeof SEQUENCE_OPERATIONS[number];
// Jobs addressed by a single `operation`: the independent `read` Job and the
// legacy complete `flash_cycle`. A single erase / program / verify is never
// a Job of its own.
export const PROGRAMMING_OPERATIONS = ["flash_cycle", "read"] as const;
export type SingleOperation = typeof PROGRAMMING_OPERATIONS[number];
export type ProgrammingOperation = SingleOperation | "programming";
export const IMAGE_OPERATIONS: ReadonlySet<string> = new Set(["flash_cycle"]);

/** The list in its fixed order; null when it is empty or not a legal Job. */
export function normalizeOperations(selected: Iterable<string>): SequenceOperation[] | null {
  const chosen = new Set(selected);
  const ordered = SEQUENCE_OPERATIONS.filter(operation => chosen.has(operation));
  if (!ordered.length || ordered.length !== chosen.size) return null;
  // Verify compares the IC with the Programming Image; an IC that was only
  // erased can never equal it.
  if (ordered.length === 2 && ordered[0] === "erase" && ordered[1] === "verify") return null;
  return ordered;
}

export function operationsTakeImage(operations: readonly string[]): boolean {
  return operations.includes("program") || operations.includes("verify");
}

// One Programming Source per Image Operation: a Programming Image the Manager
// wraps in the canonical Bundle, or the user's own canonical Bundle v3.
export type ProgrammingSource = "image" | "bundle";

export type ProgrammingPlan = {
  plan_id: string;
  ppu_alias: string;
  site_id: number;
  operation: ProgrammingOperation;
  /** The ordered list of a programming Job; null for read / legacy flash_cycle. */
  operations: SequenceOperation[] | null;
  source: ProgrammingSource | "range";
  route: ProgrammingRoute;
  bundle: {
    archive_sha256: string;
    archive_size: number;
    bundle_name: string;
    provider: string;
    profile: string;
    asset_package_id: string;
    image_filename: string;
    image_sha256: string;
    image_size: number;
    icpn: string;
  } | null;
  resource: {
    resource_set_sha256: string;
    ppu_reported: {
      state: string;
      asset_set_sha256: string | null;
      generation: number | null;
      resource_set_sha256: string | null;
    };
    reuse: boolean;
  };
  image_asset: {
    image_asset_sha256: string;
    sha256: string;
    size: number;
    load_address: number;
    format: string;
  } | null;
  job_binding: {
    operation: ProgrammingOperation;
    operations?: SequenceOperation[];
    range: { address: number; length: number };
    image_asset_sha256: string | null;
    resource_set_sha256: string;
  };
  job_binding_sha256: string;
  active_asset_set: { state: string; asset_set_sha256: string | null };
  activation_required: boolean;
  fpga_load: false;
  steps: string[];
  catalog_gate: "NOT_USED";
};

export type ProgrammingRunOutcome = "PASS" | "FAIL" | "OUTCOME_UNKNOWN" | "BLOCKED";

export type ProgrammingRun = {
  run_id: string;
  ppu_alias: string;
  site_id: number;
  /** The Manager plan this run consumed (technical diagnostics). */
  plan?: ProgrammingPlan;
  state: string;
  outcome: ProgrammingRunOutcome | null;
  reason: string | null;
  steps: Array<{ step: string; result: string; at: string; [key: string]: unknown }>;
  activation: Record<string, unknown>;
  job: {
    job_id?: string;
    state?: string;
    stage?: string | null;
    progress_percent?: number | null;
    bytes_done?: number | null;
    bytes_total?: number | null;
  } | null;
  receipt: {
    schema: "plasma.manager.programming-receipt.v3";
    job_id: string | null;
    job_state: string | null;
    operation: string | null;
    /** Planned list and the list the PPU reports it ran (programming Jobs). */
    operations: SequenceOperation[] | null;
    observed_operations: string[] | null;
    /** Per listed step: what the Manager expected and what the PPU observed. */
    expected_steps: Record<string, Record<string, unknown>> | null;
    observed_steps: Record<string, Record<string, unknown>> | null;
    range: { address: number; length: number };
    /** Read Memory only: the Manager-verified binary. */
    read_output: {
      address: number;
      bytes: number;
      sha256: string | null;
      filename: string;
      available: boolean;
    } | null;
    site_id: number | null;
    target: string;
    expected_image_sha256: string | null;
    expected_image_size: number | null;
    observed_image_sha256: string | null;
    observed_image_size: number | null;
    readback_sha256: string | null;
    bytes_verified: number | null;
    expected_resource_set_sha256: string;
    observed_resource_set_sha256: string | null;
    expected_job_binding_sha256: string;
    observed_job_binding_sha256: string | null;
    active_asset_set_sha256: string | null;
    resource_reuse: boolean;
    safe_off: boolean | null;
    flash_result: string | null;
    elapsed_ms: number | null;
  } | null;
  job_submission_count: number;
  auto_retry: "DISABLED";
  acknowledged: boolean;
};

function base(alias: string): string {
  return `/api/manager/registry/${encodeURIComponent(alias)}/bootstrap/programming`;
}

/**
 * The canonical Manager-owned programming resources (ADR 5.8). A Batch and
 * the start it is admitted with are not under a PPU, because no PPU owns
 * them. The alias-scoped entry retired in PR-C.
 */
const PROGRAMMING = "/api/manager/programming";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const payload = await response.json().catch(() => null) as
    | (T & { error?: { code?: string; message?: string } })
    | null;
  if (!response.ok || payload == null) {
    const error = payload?.error;
    throw new BootstrapApiError(
      response.status,
      error?.code ?? null,
      error?.message ?? `Programming request failed with HTTP ${response.status}`,
    );
  }
  return payload;
}

export async function getProgrammingRoutes(alias: string): Promise<ProgrammingRoute[]> {
  const payload = await request<{ ok: true; routes: ProgrammingRoute[] }>(`${base(alias)}/routes`);
  return payload.routes;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const stride = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += stride) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + stride)));
  }
  return btoa(binary);
}

export type ImageOperation = "flash_cycle";

/** One programming Job (`operations`) or a single-operation Job (`operation`). */
type JobSelector =
  | { operations: readonly SequenceOperation[] }
  | { operation: ImageOperation };

export type PlanInput =
  | ({ icpn: string; siteId: number; image: Uint8Array; filename: string } & JobSelector)
  | ({ icpn: string; siteId: number; bundle: Uint8Array } & JobSelector)
  // No Image: an erase-only list or the independent read Job on an explicit range.
  | { icpn: string; siteId: number; operations: readonly ["erase"]; address: number; length: number }
  | { icpn: string; siteId: number; operation: "read"; address: number; length: number };

export async function planProgramming(alias: string, input: PlanInput): Promise<ProgrammingPlan> {
  // The user's selection is sent as chosen; the Manager never rewrites it.
  const selector = "operations" in input
    ? { operations: [...input.operations] } : { operation: input.operation };
  const body = "image" in input
    ? {
      icpn: input.icpn, site_id: input.siteId, ...selector,
      image_base64: bytesToBase64(input.image), image_filename: input.filename,
    }
    : "bundle" in input
    ? {
      // The user's own Bundle bytes, unchanged; the Manager admits or refuses them.
      icpn: input.icpn, site_id: input.siteId, ...selector,
      bundle_base64: bytesToBase64(input.bundle),
    }
    : {
      icpn: input.icpn, site_id: input.siteId, ...selector,
      address: input.address, length: input.length,
    };
  const payload = await request<{ ok: true; plan: ProgrammingPlan }>(`${base(alias)}/plans`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return payload.plan;
}

export async function startProgramming(alias: string, planId: string): Promise<ProgrammingRun> {
  const payload = await request<{ ok: true; run: ProgrammingRun }>(`${base(alias)}/runs`, {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, confirm: PROGRAMMING_CONFIRM_TOKEN }),
  });
  return payload.run;
}

export async function getProgrammingRun(alias: string, runId: string): Promise<ProgrammingRun> {
  const payload = await request<{ ok: true; run: ProgrammingRun }>(`${base(alias)}/runs/${runId}`);
  return payload.run;
}

export async function acknowledgeProgrammingRun(alias: string, runId: string): Promise<ProgrammingRun> {
  const payload = await request<{ ok: true; run: ProgrammingRun }>(`${base(alias)}/runs/${runId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ acknowledge: PROGRAMMING_ACK_TOKEN }),
  });
  return payload.run;
}

/** Same-origin download of a PASS Read Memory run (Console -> BFF -> Manager). */
export function readOutputUrl(alias: string, runId: string): string {
  return `${base(alias)}/runs/${runId}/output`;
}

/** Fetch the Read Memory binary; the caller re-hashes it against the receipt. */
export async function getReadOutput(alias: string, runId: string): Promise<Uint8Array> {
  const response = await fetch(readOutputUrl(alias, runId), { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null;
    throw new BootstrapApiError(response.status, payload?.error?.code ?? null,
      payload?.error?.message ?? `Read Memory download failed with HTTP ${response.status}`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

// ---------------------------------------------------------------- EMode Batch
// Manager-owned Retry / Stop Policy. The Manager decides whether another
// attempt is submitted; every attempt is its own plan, run and PPU Job.
export const PROGRAMMING_STOP_TOKEN = "STOP_QUEUING";
export const MAX_RETRY_LIMIT = 5;

export type StopPolicy = { kind: "never" } | { kind: "failed_sites"; threshold: number };
export type BatchPolicy = { repeat: 1; retry_limit: number; stop_policy: StopPolicy };
// A Batch spans Sites, so it has outcomes a single run cannot have:
// PARTIAL (some Sites passed) and BLOCKED (nothing was submitted).
export type ProgrammingBatchOutcome = ProgrammingRunOutcome | "PARTIAL" | "STOPPED";

export type ProgrammingBatchAttempt = {
  attempt: number;
  /** The Manager's identity for this attempt: which PPU, Site and try it was. */
  job_key: { batch_id: string; ppu_alias: string; site_id: number; attempt: number };
  plan_id: string;
  run_id: string | null;
  job_id: string | null;
  job_binding_sha256: string;
  state: string;
  outcome: ProgrammingRunOutcome | null;
  reason: string | null;
  safe_off: boolean | null;
  /** Why a FAIL was or was not followed by another attempt. */
  retry: { eligible: boolean; reason: string; decision: "RETRY" | "NO_RETRY" } | null;
};

/** One PPU and the Sites of it this Batch covers. */
export type ProgrammingBatchTarget = { ppu_alias: string; site_ids: number[] };

/**
 * One Site of one PPU: the unit the Manager schedules, isolates and judges.
 * A Batch outcome is an aggregate of these, never a substitute for them.
 */
export type ProgrammingBatchUnit = {
  ppu_alias: string;
  site_id: number;
  status: string;
  outcome: ProgrammingBatchOutcome | null;
  reason: string | null;
  /** Whose failure it was: the Target, its state, its transaction or shared control. */
  failure_domain: string | null;
  attempts: ProgrammingBatchAttempt[];
};

export type ProgrammingBatch = {
  schema: "plasma.manager.programming-batch.v1";
  batch_id: string;
  /** The Manager-issued token this Batch was admitted with. */
  start_id: string | null;
  targets: ProgrammingBatchTarget[];
  units: ProgrammingBatchUnit[];
  /**
   * A single-Site Batch also carries these. They are a projection of the one
   * record, so read `units` for anything a multi-Site Batch must show.
   */
  ppu_alias?: string;
  site_id?: number;
  icpn: string;
  operations: SequenceOperation[];
  source: ProgrammingSource | "range";
  policy: BatchPolicy;
  state: string;
  execution_status: string;
  outcome: ProgrammingBatchOutcome | null;
  reason: string | null;
  failure_domain: string | null;
  stop_requested: boolean;
  /** Every attempt of every Site, in order. */
  attempts: ProgrammingBatchAttempt[];
  /** The run of the latest attempt (same record as a single run). */
  current_run: ProgrammingRun | null;
  /** One Site is one IC: counted once, by its final outcome. */
  counts: {
    pass: number; fail: number; blocked: number; unknown: number;
    sites: number; attempts: number;
  };
  auto_retry: "DISABLED";
};

export type BatchInput = (
  | { icpn: string; operations: readonly SequenceOperation[]; image: Uint8Array; filename: string }
  | { icpn: string; operations: readonly SequenceOperation[]; bundle: Uint8Array }
  | { icpn: string; operations: readonly ["erase"]; address: number; length: number }
) & {
  alias: string;
  siteIds: readonly number[];
  retryLimit: number;
  stopPolicy: StopPolicy;
};

/**
 * Start one Batch over a Target Set. The Batch is Manager-owned, so it is
 * started on the canonical resource rather than under a PPU, and it always
 * carries the Manager-issued start it can be reconciled by.
 */
export async function startProgrammingBatch(
  input: BatchInput, startId: string,
): Promise<ProgrammingBatch> {
  const common = {
    icpn: input.icpn,
    targets: [{ ppu_alias: input.alias, site_ids: [...input.siteIds] }],
    operations: [...input.operations],
    retry_limit: input.retryLimit, stop_policy: input.stopPolicy, repeat: 1,
    // Manager-issued: admits at most one Batch and can be reconciled later.
    start_id: startId,
  };
  const body = "image" in input
    ? { ...common, image_base64: bytesToBase64(input.image), image_filename: input.filename }
    : "bundle" in input
    ? { ...common, bundle_base64: bytesToBase64(input.bundle) }
    : { ...common, address: input.address, length: input.length };
  const payload = await request<{ ok: true; batch: ProgrammingBatch }>(`${PROGRAMMING}/batches`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return payload.batch;
}

export async function getProgrammingBatch(batchId: string): Promise<ProgrammingBatch> {
  const payload = await request<{ ok: true; batch: ProgrammingBatch }>(`${PROGRAMMING}/batches/${batchId}`);
  return payload.batch;
}

/** Stop queuing: no further attempt is submitted. Never cancels a submitted Job. */
export async function stopProgrammingBatch(batchId: string): Promise<ProgrammingBatch> {
  const payload = await request<{ ok: true; batch: ProgrammingBatch }>(`${PROGRAMMING}/batches/${batchId}/stop`, {
    method: "POST",
    body: JSON.stringify({ stop: PROGRAMMING_STOP_TOKEN }),
  });
  return payload.batch;
}

// ------------------------------------------------ Start Outcome Reconciliation
// Every Start carries a Manager-issued start ID: a run's `plan_id`, or the ID
// issued here for a Batch. The Manager journals the issue and the admission,
// so a Console that never saw the Start answer can ask what became of it.
export const PROGRAMMING_VOID_TOKEN = "VOID_UNSTARTED_START";

export type StartReconciliationState =
  | "NOT_ACCEPTED"          // proven: never admitted and can no longer be
  | "ACCEPTANCE_PENDING"    // not admitted yet; a delayed request still could be
  | "ACCEPTED_RUNNING"
  | "TERMINAL_CONFIRMED"    // PASS / FAIL / BLOCKED / STOPPED
  | "OUTCOME_UNKNOWN";      // the run is unknown, or nothing can be proven

export type StartReconciliation = {
  schema: "plasma.manager.programming-start-reconciliation.v1";
  start_id: string;
  /** Read off the run, the Target Set or the record; a Batch start has none. */
  ppu_alias: string | null;
  kind: "run" | "batch" | null;
  state: StartReconciliationState;
  reason: string | null;
  outcome: ProgrammingBatchOutcome | null;
  /** What the Manager journalled for this start; null when it has no record. */
  identity: {
    ppu_alias: string | null;
    site_id: number | null;
    targets?: ProgrammingBatchTarget[] | null;
    ppu_id: string | null;
    operation: string | null;
    operations: string[] | null;
    job_binding_sha256: string | null;
  } | null;
  run: ProgrammingRun | null;
  batch: ProgrammingBatch | null;
  /** OUTCOME_UNKNOWN run only: its Manager latch and the run to acknowledge. */
  acknowledged: boolean | null;
  unknown_run_id: string | null;
  expires_in_s: number | null;
  read_only: true;
  auto_retry: "DISABLED";
};

/**
 * Issue the start ID one Batch start must carry. Submits nothing.
 *
 * The Manager issues it under no PPU: the Batch is Manager-owned, and each
 * Target's authority is checked when the Batch is admitted. `alias` is the
 * PPU this Console is acting for; it is NOT sent to the Manager and never
 * reaches the record. The BFF uses it to require this operator's maintenance
 * capability for that PPU, which is the boundary the retired alias-scoped
 * route enforced through its path.
 */
export async function issueBatchStart(alias: string): Promise<string> {
  const payload = await request<{ ok: true; start: { start_id: string } }>(
    `${PROGRAMMING}/starts?ppu_alias=${encodeURIComponent(alias)}`, {
      method: "POST",
      body: JSON.stringify({ kind: "batch" }),
    });
  return payload.start.start_id;
}

/** Read-only. Repeating it never submits, retries or acknowledges anything. */
export async function getStartReconciliation(startId: string): Promise<StartReconciliation> {
  const payload = await request<{ ok: true; reconciliation: StartReconciliation }>(
    `${PROGRAMMING}/starts/${startId}`);
  return payload.reconciliation;
}

/**
 * Operator: a start the Manager never admitted may never be admitted.
 *
 * `alias` is the PPU this Console is acting for, for the BFF capability check
 * only. When the Manager already has a PPU on record for this start, that
 * record decides and this claim cannot widen it.
 */
export async function voidStart(startId: string, alias: string): Promise<StartReconciliation> {
  const payload = await request<{ ok: true; reconciliation: StartReconciliation }>(
    `${PROGRAMMING}/starts/${startId}/void?ppu_alias=${encodeURIComponent(alias)}`, {
      method: "POST",
      body: JSON.stringify({ void: PROGRAMMING_VOID_TOKEN }),
    });
  return payload.reconciliation;
}
