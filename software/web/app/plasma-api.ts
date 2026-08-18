export type JobState =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "cancelled"
  | "timeout"
  | "aborted";

export type Operation = "erase" | "program" | "verify" | "read";

export type ChannelSnapshot = {
  channel_id: number;
  enabled: boolean;
  state: string;
  current_job_id: string | null;
  queued_jobs: number;
  interface: string | null;
  target: string | null;
};

export type JobSnapshot = {
  job_id: string;
  channel_id: number;
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
    throw new Error("Python API URL 必須使用 http:// 或 https://");
  }
  return url.toString().replace(/\/$/, "");
}

function normalizeJobSnapshot(job: JobSnapshot): JobSnapshot {
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
        ? `${payload.error.error_code}: ${payload.error.message ?? "Python API error"}`
        : payload.error?.message ?? `Python API HTTP ${response.status}`;
      throw new PlasmaApiError(detail, response.status);
    }
    return payload;
  } catch (error) {
    if (error instanceof PlasmaApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new PlasmaApiError("Python API 連線逾時");
    }
    throw new PlasmaApiError(
      error instanceof Error ? error.message : "無法連接 Python API",
    );
  } finally {
    window.clearTimeout(timer);
  }
}

export async function getChannels(apiBase: string): Promise<ChannelSnapshot[]> {
  const payload = await requestJson<{ ok: boolean; channels: ChannelSnapshot[] }>(
    apiBase,
    "/api/status",
  );
  return payload.channels;
}

export async function getJob(
  apiBase: string,
  jobId: string,
): Promise<JobSnapshot> {
  const payload = await requestJson<{ ok: boolean; job: JobSnapshot }>(
    apiBase,
    `/api/status?job=${encodeURIComponent(jobId)}`,
  );
  return normalizeJobSnapshot(payload.job);
}

export async function startJob(
  apiBase: string,
  options: {
    channelId: number;
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
  const payload = await requestJson<{ ok: boolean; job: JobSnapshot }>(
    apiBase,
    "/api/jobs",
    {
      method: "POST",
      body: JSON.stringify({
        channel_id: options.channelId,
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