import { ensureGatewaySettings, gatewayStatusObservationTimeoutMs } from "./gateway-settings-api";

export type JobState =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "error"
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
  rest_contract_version?: string;
  programming_asset_scope?: string;
  supported_asset_types?: string[];
  supported_asset_formats?: string[];
  implemented_normalizers?: Array<{
    asset_type: string;
    asset_format: string;
    output: string;
  }>;
  facilities: EngineeringFacilityTarget[];
};

export type EngineeringSession = {
  session_id: string;
  programming_asset_cache_scope?: string;
  previous_session_cleared: boolean;
};

export type ProgrammingAssetFingerprint = {
  asset_name: string;
  asset_type: "image";
  asset_format: "binary";
  asset_size: number;
  asset_sha256: string;
};

type ProgrammingAssetCacheStatus = ProgrammingAssetFingerprint & {
  cache_hit: boolean;
  uploaded?: boolean;
};

export type AssetTransferEvent = ProgrammingAssetFingerprint & {
  kind: "cache_check" | "cache_hit" | "cache_miss" | "upload_start" | "upload_complete";
};

export type JobTargetDeviceRequest = {
  vendor: string;
  identifier: string;
};

type StatusPayload = {
  ok: boolean;
  ppu?: PPUSnapshot;
  sites?: SiteSnapshot[];
};

export type JobError = {
  message?: string;
  error_code?: string;
  failure_source?: string | null;
  retry_count?: number;
};

export type JobAttempt = {
  attempt: number;
  state: JobState;
  started_at: string;
  finished_at: string;
  elapsed_ms: number;
  retry_scheduled: boolean;
  error?: JobError | null;
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
  attempt?: number;
  attempt_history?: JobAttempt[];
  retry_exhausted?: boolean;
  result?: {
    state: JobState;
    attempts?: number;
    attempt_history?: JobAttempt[];
    retry_exhausted?: boolean;
    output_files?: string[];
    error?: JobError | null;
  };
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
    readonly errorCode?: string,
    readonly transient = false,
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

const terminalJobStates = new Set<JobState>([
  "success",
  "failed",
  "error",
  "cancelled",
  "timeout",
  "aborted",
]);
const ppuExecutionListeners = new Set<() => void>();
const activeExecutionJobs = new Set<string>();
const inFlightJobSnapshots = new Map<string, Promise<JobSnapshot>>();
let pendingJobSubmissions = 0;
let lastExecutionActivityCount = 0;

function executionJobKey(apiBase: string, jobId: string): string {
  return `${apiBase}|${jobId}`;
}

function executionActivityCount(): number {
  return pendingJobSubmissions + activeExecutionJobs.size;
}

function emitPpuExecutionActivityIfChanged(): void {
  const next = executionActivityCount();
  if (next === lastExecutionActivityCount) return;
  lastExecutionActivityCount = next;
  ppuExecutionListeners.forEach(listener => listener());
}

function beginJobSubmission(): void {
  pendingJobSubmissions += 1;
  emitPpuExecutionActivityIfChanged();
}

function endJobSubmission(): void {
  pendingJobSubmissions = Math.max(0, pendingJobSubmissions - 1);
  emitPpuExecutionActivityIfChanged();
}

function syncExecutionJob(apiBase: string, job: JobSnapshot): void {
  const key = executionJobKey(apiBase, job.job_id);
  if (terminalJobStates.has(job.state)) activeExecutionJobs.delete(key);
  else activeExecutionJobs.add(key);
  emitPpuExecutionActivityIfChanged();
}

function markExecutionJobActive(apiBase: string, jobId: string): void {
  activeExecutionJobs.add(executionJobKey(apiBase, jobId));
  emitPpuExecutionActivityIfChanged();
}

export function subscribePpuExecutionActivity(listener: () => void): () => void {
  ppuExecutionListeners.add(listener);
  return () => ppuExecutionListeners.delete(listener);
}

export function getPpuExecutionActivityCount(): number {
  return executionActivityCount();
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

function engineeringGatewayApiBase(apiBase: string): string | null {
  const marker = "/api/engineering/targets/";
  const index = apiBase.indexOf(marker);
  return index >= 0 ? apiBase.slice(0, index) : null;
}

async function statusObservationTimeoutMs(apiBase: string, requestedTimeoutMs?: number): Promise<number | undefined> {
  const gatewayBase = engineeringGatewayApiBase(apiBase);
  if (gatewayBase === null) return requestedTimeoutMs;
  try {
    const settings = await ensureGatewaySettings(gatewayBase);
    return gatewayStatusObservationTimeoutMs(settings);
  } catch (error) {
    throw new PlasmaApiError(
      `Gateway communication policy unavailable: ${error instanceof Error ? error.message : "unknown error"}`,
      undefined,
      undefined,
      true,
    );
  }
}

function normalizeJobSnapshot(job: JobSnapshot): JobSnapshot {
  if (!Number.isInteger(job.site_id) || job.site_id < 1) {
    throw new PlasmaApiError("Job snapshot is missing a valid site_id");
  }
  if (job.state !== "cancelled" || !job.result?.error) return job;
  return {
    ...job,
    result: {
      ...job.result,
      error: null,
    },
  };
}

async function requestJson<T>(
  apiBase: string,
  path: string,
  init?: RequestInit,
  timeoutMs = 10_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();
  const method = init?.method ?? "GET";
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
      const errorCode = payload.error?.error_code;
      throw new PlasmaApiError(
        detail,
        response.status,
        errorCode,
        response.status >= 500 || errorCode === "E2001" || errorCode === "E2002",
      );
    }
    return payload;
  } catch (error) {
    if (error instanceof PlasmaApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new PlasmaApiError(
        `Plasma Web REST Gateway request timed out · ${method} ${path} · ${Date.now() - startedAt} ms`,
        undefined,
        undefined,
        true,
      );
    }
    throw new PlasmaApiError(
      `${error instanceof Error ? error.message : "Plasma Web REST Gateway connection failed"} · ${method} ${path} · ${Date.now() - startedAt} ms`,
      undefined,
      undefined,
      true,
    );
  } finally {
    window.clearTimeout(timer);
  }
}

export async function getEngineeringTargets(apiBase: string): Promise<EngineeringTargetCatalog> {
  return await requestJson<EngineeringTargetCatalog>(apiBase, "/api/engineering/targets");
}

export async function getGatewayLiveness(apiBase: string, timeoutMs?: number): Promise<void> {
  await requestJson<{ ok: boolean; gateway: string }>(apiBase, "/api/health/live", undefined, timeoutMs);
}

export async function beginEngineeringSession(
  apiBase: string,
  previousSessionId?: string,
): Promise<EngineeringSession> {
  const payload = await requestJson<{ ok: boolean; session: EngineeringSession }>(
    apiBase,
    "/api/engineering/session",
    {
      method: "POST",
      body: JSON.stringify(previousSessionId ? { previous_session_id: previousSessionId } : {}),
    },
  );
  return payload.session;
}

const fingerprintByFile = new WeakMap<File, Promise<ProgrammingAssetFingerprint>>();
const assetEnsureInFlight = new Map<string, Promise<ProgrammingAssetFingerprint>>();

async function fingerprintFile(file: File): Promise<ProgrammingAssetFingerprint> {
  let pending = fingerprintByFile.get(file);
  if (!pending) {
    pending = file.arrayBuffer().then(async buffer => {
      const digest = await window.crypto.subtle.digest("SHA-256", buffer);
      const assetSha256 = Array.from(new Uint8Array(digest))
        .map(value => value.toString(16).padStart(2, "0"))
        .join("");
      return {
        asset_name: file.name,
        asset_type: "image" as const,
        asset_format: "binary" as const,
        asset_size: file.size,
        asset_sha256: assetSha256,
      };
    });
    fingerprintByFile.set(file, pending);
  }
  return await pending;
}

function emitAssetEvent(
  callback: ((event: AssetTransferEvent) => void) | undefined,
  kind: AssetTransferEvent["kind"],
  fingerprint: ProgrammingAssetFingerprint,
): void {
  callback?.({ kind, ...fingerprint });
}

async function ensureEngineeringAsset(
  apiBase: string,
  sessionId: string,
  file: File,
  onAssetEvent?: (event: AssetTransferEvent) => void,
): Promise<ProgrammingAssetFingerprint> {
  const fingerprint = await fingerprintFile(file);
  const key = `${sessionId}|${apiBase}|${fingerprint.asset_sha256}`;
  const existing = assetEnsureInFlight.get(key);
  if (existing) return await existing;
  const ensure = (async () => {
    emitAssetEvent(onAssetEvent, "cache_check", fingerprint);
    const checked = await requestJson<{
      ok: boolean;
      programming_asset: ProgrammingAssetCacheStatus;
    }>(
      apiBase,
      "/api/programming-assets/check",
      {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          ...fingerprint,
        }),
      },
    );
    if (checked.programming_asset.cache_hit) {
      emitAssetEvent(onAssetEvent, "cache_hit", fingerprint);
      return fingerprint;
    }

    emitAssetEvent(onAssetEvent, "cache_miss", fingerprint);
    emitAssetEvent(onAssetEvent, "upload_start", fingerprint);
    await requestJson(
      apiBase,
      `/api/programming-assets?session_id=${encodeURIComponent(sessionId)}&name=${encodeURIComponent(fingerprint.asset_name)}&type=${encodeURIComponent(fingerprint.asset_type)}&format=${encodeURIComponent(fingerprint.asset_format)}&sha256=${encodeURIComponent(fingerprint.asset_sha256)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      },
      120_000,
    );
    emitAssetEvent(onAssetEvent, "upload_complete", fingerprint);
    return fingerprint;
  })();
  assetEnsureInFlight.set(key, ensure);
  try {
    return await ensure;
  } finally {
    assetEnsureInFlight.delete(key);
  }
}

export async function getPPUStatus(apiBase: string, timeoutMs?: number): Promise<PPUStatus> {
  const observationTimeout = await statusObservationTimeoutMs(apiBase, timeoutMs);
  const payload = await requestJson<StatusPayload>(apiBase, "/api/status", undefined, observationTimeout);
  return {
    ppu: payload.ppu,
    sites: payload.sites ?? [],
  };
}

export async function getSites(apiBase: string): Promise<SiteSnapshot[]> {
  return (await getPPUStatus(apiBase)).sites;
}

export async function getJob(
  apiBase: string,
  jobId: string,
  timeoutMs?: number,
): Promise<JobSnapshot> {
  const key = executionJobKey(apiBase, jobId);
  const existing = inFlightJobSnapshots.get(key);
  if (existing) return await existing;
  const request = (async () => {
    const observationTimeout = await statusObservationTimeoutMs(apiBase, timeoutMs);
    const payload = await requestJson<{ ok: boolean; job: JobSnapshot }>(
      apiBase,
      `/api/status?job=${encodeURIComponent(jobId)}`,
      undefined,
      observationTimeout,
    );
    const job = normalizeJobSnapshot(payload.job);
    syncExecutionJob(apiBase, job);
    return job;
  })();
  inFlightJobSnapshots.set(key, request);
  try {
    return await request;
  } finally {
    inFlightJobSnapshots.delete(key);
  }
}

export async function startJob(
  apiBase: string,
  options: {
    siteId: number;
    operation: Operation;
    assetFile?: File | null;
    engineeringSessionId?: string;
    allowSyntheticMockImage?: boolean;
    offset?: number;
    length?: number;
    targetDevice?: JobTargetDeviceRequest;
    requestTimeoutMs?: number;
    submissionGuard?: () => boolean;
    onAssetEvent?: (event: AssetTransferEvent) => void;
  },
): Promise<JobSnapshot> {
  beginJobSubmission();
  try {
    const usesAsset = options.operation === "program" || options.operation === "verify";
    const engineeringTarget = apiBase.includes("/api/engineering/targets/");
    const syntheticMockImage = usesAsset && !options.assetFile && options.allowSyntheticMockImage === true;
    let fingerprint: ProgrammingAssetFingerprint | null = null;
    let assetBase64 = "";

    if (usesAsset) {
      if (!options.assetFile && !syntheticMockImage) {
        throw new PlasmaApiError("Program and Verify require an Image Asset");
      }
      if (syntheticMockImage && !engineeringTarget) {
        throw new PlasmaApiError("Synthetic Mock Image is only valid for an Engineering Mock target");
      }
      if (engineeringTarget && !options.engineeringSessionId) {
        throw new PlasmaApiError("Engineering connection session is not ready");
      }
      if (options.assetFile) {
        fingerprint = await fingerprintFile(options.assetFile);
        if (engineeringTarget) {
          fingerprint = await ensureEngineeringAsset(
            apiBase,
            options.engineeringSessionId!,
            options.assetFile,
            options.onAssetEvent,
          );
        } else {
          assetBase64 = await fileToBase64(options.assetFile);
        }
      }
    }

    if (options.submissionGuard && !options.submissionGuard()) {
      throw new PlasmaSubmissionBlockedError();
    }

    const body: Record<string, unknown> = {
      site_id: options.siteId,
      operation: options.operation,
    };
    if (engineeringTarget && options.targetDevice) {
      body.target_device = {
        vendor: options.targetDevice.vendor,
        identifier: options.targetDevice.identifier,
      };
    }
    if (usesAsset && engineeringTarget && options.engineeringSessionId) {
      body.session_id = options.engineeringSessionId;
      if (fingerprint) body.asset_sha256 = fingerprint.asset_sha256;
    } else if (fingerprint && usesAsset) {
      Object.assign(body, fingerprint, {
        asset_base64: assetBase64,
        timeout_s: 30,
      });
    }
    if (options.operation === "read") {
      body.offset = options.offset ?? 0;
      body.length = options.length ?? 256;
    }

    const payload = await requestJson<{ ok: boolean; job: JobSnapshot }>(
      apiBase,
      "/api/jobs",
      { method: "POST", body: JSON.stringify(body) },
      options.requestTimeoutMs,
    );
    const job = normalizeJobSnapshot(payload.job);
    syncExecutionJob(apiBase, job);
    return job;
  } finally {
    endJobSubmission();
  }
}

export async function cancelJob(
  apiBase: string,
  jobId: string,
  timeoutMs?: number,
): Promise<void> {
  const key = executionJobKey(apiBase, jobId);
  const wasTracked = activeExecutionJobs.has(key);
  markExecutionJobActive(apiBase, jobId);
  try {
    await requestJson(
      apiBase,
      `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST", body: "{}" },
      timeoutMs,
    );
  } catch (error) {
    if (!wasTracked) {
      activeExecutionJobs.delete(key);
      emitPpuExecutionActivityIfChanged();
    }
    throw error;
  }
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
