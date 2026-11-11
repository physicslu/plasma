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

// Exactly the programming Operations of the Job Binding contract; the
// Route Profile decides which of them a Site offers.
export const PROGRAMMING_OPERATIONS = ["flash_cycle", "program", "verify", "erase", "read"] as const;
export type ProgrammingOperation = typeof PROGRAMMING_OPERATIONS[number];
export const IMAGE_OPERATIONS: ReadonlySet<string> = new Set(["flash_cycle", "program", "verify"]);

// One Programming Source per Image Operation: a Programming Image the Manager
// wraps in the canonical Bundle, or the user's own canonical Bundle v3.
export type ProgrammingSource = "image" | "bundle";

export type ProgrammingPlan = {
  plan_id: string;
  ppu_alias: string;
  site_id: number;
  operation: ProgrammingOperation;
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
    schema: "plasma.manager.programming-receipt.v2";
    job_id: string | null;
    job_state: string | null;
    operation: string | null;
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

export type ImageOperation = "flash_cycle" | "program" | "verify";

export type PlanInput =
  | { icpn: string; siteId: number; operation: ImageOperation; image: Uint8Array; filename: string }
  | { icpn: string; siteId: number; operation: ImageOperation; bundle: Uint8Array }
  | { icpn: string; siteId: number; operation: "erase" | "read"; address: number; length: number };

export async function planProgramming(alias: string, input: PlanInput): Promise<ProgrammingPlan> {
  // The user's Operation is sent as chosen; the Manager never rewrites it.
  const body = "image" in input
    ? {
      icpn: input.icpn, site_id: input.siteId, operation: input.operation,
      image_base64: bytesToBase64(input.image), image_filename: input.filename,
    }
    : "bundle" in input
    ? {
      // The user's own Bundle bytes, unchanged; the Manager admits or refuses them.
      icpn: input.icpn, site_id: input.siteId, operation: input.operation,
      bundle_base64: bytesToBase64(input.bundle),
    }
    : {
      icpn: input.icpn, site_id: input.siteId, operation: input.operation,
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
