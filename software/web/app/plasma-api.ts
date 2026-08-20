export type JobState =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "cancelled"
  | "timeout"
  | "aborted";

export type Operation = "erase" | "program" | "verify" | "read";

export type SiteSnapshot = {
  site_id: number;
  enabled: boolean;
  state: string;
  current_job_id: string | null;
  queued_jobs: number;
  interface: string | null;
  target: string | null;
};

export type PPUCapabilities = {
  max_supported_sites: number;
  operations: Operation[];
};

export type PPUSnapshot = {
  ppu_id: string;
  facility_id: string;
  model: string;
  display_name: string;
  site_count: number;
  enabled_site_count: number;
  capabilities: PPUCapabilities;
};

export type PPUStatus = {
  ppu?: PPUSnapshot;
  sites: SiteSnapshot[];
};

export type EngineeringPPUTarget = {
  ppu_id: string;
  display_name: string;
  model: string;
  site_count: number;
  provider: string;
};

export type EngineeringFacilityTarget = {
  facility_id: string;
  display_name: string;
  ppus: EngineeringPPUTarget[];
};

export type EngineeringTargetCatalog = {
  ok: boolean;
  provider: string;
  facility_count: number;
  ppu_count: number;
  site_count: number;
  facilities: EngineeringFacilityTarget[];
};

// Transitional shapes accepted only from protocol/API v3.1 backends.
type LegacyChannelSnapshot = {
  channel_id: number;
  enabled: boolean;
  state: string;
  current_job_id: string | null;
  queued_jobs: number;
  interface: string | null;
  target: string | null;
};

type LegacyProgrammerSnapshot = {
  programmer_id: string;
  site_id: string;
  model: string;
  display_name: string;
  channel_count: number;
  enabled_channel_count: number;
  capabilities: {
    max_supported_channels: number;
    operations: Operation[];
  };
};

type StatusPayload = {
  ok: boolean;
  ppu?: PPUSnapshot;
  sites?: SiteSnapshot[];
  programmer?: LegacyProgrammerSnapshot;
  channels?: LegacyChannelSnapshot[];
};

export type JobSnapshot = {
  job_id: string;
  site_id: number;
  operation: Operation;
  state: JobState;
  cancel_requested: boolean;
  stage: string | null;
  stage_state: string | null;
  stage_progress_percent: number;
  progress_percent: number;
  bytes_done: number | null;
  bytes_total: number | null;
  result?: {
    state: JobState;
    output_files?: string[];
    error?: { message?: string } | null;
  };
};

type WireJobSnapshot = Omit<JobSnapshot, "site_id"> & {
  site_id?: number;
  channel_id?: number;
};

type ApiErrorPayload = {
  error?: { message?: string; error_code?: string };
};

export const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_PLASMA_API_URL ?? "https://plasma.open4th.com";

export class PlasmaApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "PlasmaApiError";
  }
}

export class PlasmaSubmissionBlockedError extends Error {
  constructor() {
    super("Job submission blocked by cancel barrier");
    this.name = "PlasmaSubmissionBlockedError";
  }
}

export function normalizeApiBase(value: string): string {
  const url = new URL(value.trim());
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Plasma Web REST Gateway URL 必須使用 http:// 或 https://");
  }
  return url.toString().replace(/\/$/, "");
}

export function engineeringTargetApiBase(
  apiBase: string,
  facilityId: string,
  ppuId: string,
): string {
  return `${apiBase}/api/engineering/targets/${encodeURIComponent(facilityId)}/${encodeURIComponent(ppuId)}`;
}

function normalizeJobSnapshot(job: WireJobSnapshot): JobSnapshot {
  const siteId = job.site_id ?? (job.channel_id === undefined ? undefined : job.channel_id + 1);
  if (siteId === undefined) {
    throw new PlasmaApiError("Job snapshot is missing site_id");
  }
  const normalized = {
    ...job,
    site_id: siteId,
  } as JobSnapshot & { channel_id?: number };
  delete normalized.channel_id;
  if (normalized.state !== "cancelled" || !normalized.result?.error) return normalized;
  return {
    ...normalized,
    result: {
      ...normalized.result,
      error: null,
    },
  };
}

function legacyPPU(programmer: LegacyProgrammerSnapshot): PPUSnapshot {
  return {
    ppu_id: programmer.programmer_id,
    facility_id: programmer.site_id,
    model: programmer.model,
    display_name: programmer.display_name,
    site_count: programmer.channel_count,
    enabled_site_count: programmer.enabled_channel_count,
    capabilities: {
      max_supported_sites: programmer.capabilities.max_supported_channels,
      operations: programmer.capabilities.operations,
    },
  };
}

function legacySite(channel: LegacyChannelSnapshot): SiteSnapshot {
  return {
    site_id: channel.channel_id + 1,
    enabled: channel.enabled,
    state: channel.state,
    current_job_id: channel.current_job_id,
    queued_jobs: channel.queued_jobs,
    interface: channel.interface,
    target: channel.target,
  };
}

async function requestJson<T>(
  apiBase: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(`${apiBase}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });
    const payload = (await response.json()) as T & ApiErrorPayload;
    if (!response.ok) {
      const detail = payload.error?.error_code
        ? `${payload.error.error_code}: ${payload.error.message ?? "Plasma REST error"}`
        : payload.error?.message ?? `Plasma REST HTTP ${response.status}`;
      throw new PlasmaApiError(detail, response.status);
    }
    return payload;
  } catch (error) {
    if (error instanceof PlasmaApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new PlasmaApiError("Plasma Web REST Gateway 連線逾時");
    }
    throw new PlasmaApiError(
      error instanceof Error ? error.message : "無法連接 Plasma Web REST Gateway",
    );
  } finally {
    window.clearTimeout(timer);
  }
}

export async function getEngineeringTargets(apiBase: string): Promise<EngineeringTargetCatalog> {
  return await requestJson<EngineeringTargetCatalog>(apiBase, "/api/engineering/targets");
}

export async function getPPUStatus(apiBase: string): Promise<PPUStatus> {
  const payload = await requestJson<StatusPayload>(apiBase, "/api/status");
  return {
    ppu: payload.ppu ?? (payload.programmer ? legacyPPU(payload.programmer) : undefined),
    sites: payload.sites ?? (payload.channels ?? []).map(legacySite),
  };
}

export async function getSites(apiBase: string): Promise<SiteSnapshot[]> {
  return (await getPPUStatus(apiBase)).sites;
}

export async function getJob(
  apiBase: string,
  jobId: string,
): Promise<JobSnapshot> {
  const payload = await requestJson<{ ok: boolean; job: WireJobSnapshot }>(
    apiBase,
    `/api/status?job=${encodeURIComponent(jobId)}`,
  );
  return normalizeJobSnapshot(payload.job);
}

export async function startJob(
  apiBase: string,
  options: {
    siteId: number;
    operation: Operation;
    firmware?: File | null;
    offset?: number;
    length?: number;
    submissionGuard?: () => boolean;
  },
): Promise<JobSnapshot> {
  const firmwareBase64 = options.firmware
    ? await fileToBase64(options.firmware)
    : "";
  if (options.submissionGuard && !options.submissionGuard()) {
    throw new PlasmaSubmissionBlockedError();
  }
  const payload = await requestJson<{ ok: boolean; job: WireJobSnapshot }>(
    apiBase,
    "/api/jobs",
    {
      method: "POST",
      body: JSON.stringify({
        site_id: options.siteId,
        operation: options.operation,
        firmware_name: options.firmware?.name,
        firmware_base64: firmwareBase64,
        ...(options.operation === "read" ? {
          offset: options.offset ?? 0,
          length: options.length ?? 256,
        } : {}),
        timeout_s: 30,
      }),
    },
  );
  return normalizeJobSnapshot(payload.job);
}

export async function cancelJob(
  apiBase: string,
  jobId: string,
): Promise<void> {
  await requestJson(
    apiBase,
    `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST", body: "{}" },
  );
}

export function readDownloadUrl(apiBase: string, jobId: string, filename: string): string {
  return `${apiBase}/api/jobs/${encodeURIComponent(jobId)}/files/${encodeURIComponent(filename)}`;
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const chunks: string[] = [];
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    chunks.push(
      String.fromCharCode(...bytes.subarray(offset, offset + chunkSize)),
    );
  }
  return window.btoa(chunks.join(""));
}
