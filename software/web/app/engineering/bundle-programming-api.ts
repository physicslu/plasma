import { BootstrapApiError } from "./ppu-bootstrap-api";

// Console-driven Bundle programming (owner Gate 1, 2026-11-09).
// Browser -> same-origin BFF -> Manager. The Manager resolves the
// Programming Route, builds the canonical Bundle v3, issues owner
// authorizations, runs B1/B2/B3 only when the Active Set differs and
// submits exactly one flash_cycle Job. The Browser never builds or signs
// a Bundle and never talks to the PPU directly.

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

export type ProgrammingPlan = {
  plan_id: string;
  ppu_alias: string;
  site_id: number;
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
  };
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
    job_id: string | null;
    job_state: string | null;
    readback_sha256: string | null;
    image_sha256: string;
    image_size: number;
    bytes_verified: number | null;
    safe_off: boolean | null;
    flash_result: string | null;
    asset_set_sha256: string;
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

export async function planProgramming(
  alias: string,
  input: { icpn: string; siteId: number; image: Uint8Array; filename: string },
): Promise<ProgrammingPlan> {
  const payload = await request<{ ok: true; plan: ProgrammingPlan }>(`${base(alias)}/plans`, {
    method: "POST",
    body: JSON.stringify({
      icpn: input.icpn,
      site_id: input.siteId,
      image_base64: bytesToBase64(input.image),
      image_filename: input.filename,
    }),
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
