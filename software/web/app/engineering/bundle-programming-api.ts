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
  sites: number[];
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
