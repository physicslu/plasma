import type { Operation } from "./plasma-api";
import type { MockBatchRuntimeSnapshot } from "./mock-runtime-api";
import { publishServerBatchSnapshot } from "./server-batch-snapshot-store";

export type ServerBatchState =
  | "queued"
  | "running"
  | "stopping"
  | "success"
  | "partial"
  | "error"
  | "cancelled";

export type ServerBatchSiteState =
  | "ready"
  | "running"
  | "success"
  | "faulted"
  | "error"
  | "stopped"
  | "cancelled";

export type BatchExecutionPolicy = {
  repeat_count: number;
  site_retry_limit: number;
  failed_site_stop_threshold: number | null;
};

export type BatchTargetDeviceSnapshot = {
  vendor: string;
  family: string;
  identifier: string;
  identifier_kind: string;
  icpn: string | null;
};

export type BatchTargetDeviceRequest = {
  vendor: string;
  identifier: string;
};

export type BatchOperationStatistics = {
  logical_executions: number;
  attempts: number;
  retries: number;
  successful_executions: number;
  failed_executions: number;
  error_executions: number;
  cancelled_executions: number;
  failed_attempts: number;
  error_attempts: number;
  cancelled_attempts: number;
  attempt_failure_rate: number;
};

export type BatchSiteSnapshot = {
  facility_id: string;
  ppu_id: string;
  site_id: number;
  key: string;
  state: ServerBatchSiteState;
  current_round: number;
  completed_rounds: number;
  current_operation: Operation | null;
  current_job_id: string | null;
  progress_percent: number;
  total_attempts: number;
  retry_count: number;
  final_failures: number;
  faulted_round: number | null;
  faulted_operation: Operation | null;
  last_failure_source: string | null;
  error: { message?: string; error_code?: string; failure_source?: string | null } | null;
  operation_statistics: Partial<Record<Operation, BatchOperationStatistics>>;
};

export type ServerBatchSnapshot = {
  batch_id: string;
  state: ServerBatchState;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  operations: Operation[];
  execution_policy: BatchExecutionPolicy;
  target_device: BatchTargetDeviceSnapshot | null;
  asset: {
    name: string;
    asset_type: string;
    asset_format: string;
    size_bytes: number;
    sha256: string;
  } | null;
  read: { offset: number; length: number };
  cancel_requested: boolean;
  stop_reason: string | null;
  error: {
    message?: string;
    error_code?: string;
    faulted_site_count?: number;
    threshold?: number;
  } | null;
  faulted_site_count: number;
  site_counts: Record<ServerBatchSiteState, number>;
  operation_statistics: Partial<Record<Operation, BatchOperationStatistics>>;
  sites: BatchSiteSnapshot[];
  mock_runtime?: MockBatchRuntimeSnapshot;
};

export type BatchTargetRequest = {
  facility_id: string;
  ppu_id: string;
  site_ids: number[];
};

export type CreateServerBatchOptions = {
  sessionId?: string | null;
  targets: BatchTargetRequest[];
  operations: Operation[];
  executionPolicy: BatchExecutionPolicy;
  targetDevice?: BatchTargetDeviceRequest | null;
  assetFile?: File | null;
  allowSyntheticMockImage?: boolean;
  readOffset?: number;
  readLength?: number;
};

type BatchPayload = {
  ok: boolean;
  rest_contract_version?: string;
  batch: ServerBatchSnapshot;
};

type ErrorPayload = {
  error?: { message?: string; error_code?: string; error_type?: string };
};

export class ServerBatchApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ServerBatchApiError";
  }
}

export const terminalServerBatchStates = new Set<ServerBatchState>([
  "success",
  "partial",
  "error",
  "cancelled",
]);

async function requestBatchJson<T>(
  apiBase: string,
  path: string,
  init?: RequestInit,
  timeoutMs = 15_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
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
    const payload = (await response.json()) as T & ErrorPayload;
    if (!response.ok) {
      const error = payload.error;
      const detail = error?.error_code
        ? `${error.error_code}: ${error.message ?? error.error_type ?? "Batch REST error"}`
        : error?.message ?? `Batch REST HTTP ${response.status}`;
      throw new ServerBatchApiError(detail, response.status);
    }
    return payload;
  } catch (error) {
    if (error instanceof ServerBatchApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ServerBatchApiError("Plasma Batch REST request timed out");
    }
    throw new ServerBatchApiError(error instanceof Error ? error.message : "Batch REST request failed");
  } finally {
    window.clearTimeout(timer);
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, Math.min(offset + chunkSize, bytes.length));
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

async function encodeProgrammingAsset(file: File) {
  if (file.size <= 0) {
    throw new ServerBatchApiError("Programming Asset must not be empty");
  }
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const digest = await window.crypto.subtle.digest("SHA-256", buffer);
  const sha256 = Array.from(new Uint8Array(digest))
    .map(value => value.toString(16).padStart(2, "0"))
    .join("");
  return {
    asset_name: file.name,
    asset_type: "image",
    asset_format: "binary",
    asset_size: file.size,
    asset_sha256: sha256,
    asset_base64: bytesToBase64(bytes),
  };
}

function observeBatchSnapshot(snapshot: ServerBatchSnapshot): ServerBatchSnapshot {
  publishServerBatchSnapshot(snapshot);
  return snapshot;
}

export async function createServerBatch(
  apiBase: string,
  options: CreateServerBatchOptions,
): Promise<ServerBatchSnapshot> {
  const usesAsset = options.operations.some(operation => operation === "program" || operation === "verify");
  if (usesAsset && !options.assetFile && !options.allowSyntheticMockImage) {
    throw new ServerBatchApiError("Program / Verify Batch requires one Programming Asset");
  }
  if (usesAsset && !options.sessionId) {
    throw new ServerBatchApiError("Program / Verify Batch requires an Engineering session");
  }
  const asset = usesAsset && options.assetFile
    ? await encodeProgrammingAsset(options.assetFile)
    : undefined;
  const payload = await requestBatchJson<BatchPayload>(
    apiBase,
    "/api/batches",
    {
      method: "POST",
      body: JSON.stringify({
        ...(options.sessionId ? { session_id: options.sessionId } : {}),
        targets: options.targets,
        operations: options.operations,
        execution_policy: options.executionPolicy,
        ...(options.targetDevice ? { target_device: options.targetDevice } : {}),
        ...(asset ? { asset } : {}),
        read: {
          offset: options.readOffset ?? 0,
          length: options.readLength ?? 256,
        },
      }),
    },
    120_000,
  );
  return observeBatchSnapshot(payload.batch);
}

export async function getServerBatch(apiBase: string, batchId: string): Promise<ServerBatchSnapshot> {
  const payload = await requestBatchJson<BatchPayload>(
    apiBase,
    `/api/batches/${encodeURIComponent(batchId)}`,
  );
  return observeBatchSnapshot(payload.batch);
}

export async function cancelServerBatch(apiBase: string, batchId: string): Promise<ServerBatchSnapshot> {
  const payload = await requestBatchJson<BatchPayload>(
    apiBase,
    `/api/batches/${encodeURIComponent(batchId)}/cancel`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return observeBatchSnapshot(payload.batch);
}

export async function cancelServerBatchPPU(
  apiBase: string,
  batchId: string,
  facilityId: string,
  ppuId: string,
): Promise<ServerBatchSnapshot> {
  const payload = await requestBatchJson<BatchPayload>(
    apiBase,
    `/api/batches/${encodeURIComponent(batchId)}/targets/${encodeURIComponent(facilityId)}/${encodeURIComponent(ppuId)}/cancel`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return observeBatchSnapshot(payload.batch);
}