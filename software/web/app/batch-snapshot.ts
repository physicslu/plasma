/**
 * Browser view of a Manager Programming Batch (`/api/programming/batches`).
 * Every Batch, including a single Programming (1 Site x 1 Cycle), is owned by
 * the Plasma Manager; the PPU runs no Batch (U10).
 */
import type { Operation } from "./plasma-api";

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
  /** Manager Manual Repeat: false = same-IC Debug (Cycles are not distinct ICs). */
  replace_ic_before_next_cycle?: boolean;
};

export type BatchTargetDeviceSnapshot = {
  vendor: string;
  family: string;
  identifier: string;
  identifier_kind: string;
  icpn: string | null;
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
  /** Settled rounds; for a Manager Repeat Site, settled Cycles (PASS + FAIL). */
  completed_rounds: number;
  /** Manager Repeat only: PASS Cycles of this Site (absent: completed_rounds are PASS rounds). */
  pass_rounds?: number;
  current_operation: Operation | null;
  current_job_id: string | null;
  progress_percent: number;
  total_attempts: number;
  retry_count: number;
  final_failures: number;
  faulted_round: number | null;
  faulted_operation: Operation | null;
  last_failure_source: string | null;
  communication_state?: "connected" | "reconnecting" | "failed";
  communication_attempt?: number;
  error: { message?: string; error_code?: string; failure_source?: string | null } | null;
  operation_statistics: Partial<Record<Operation, BatchOperationStatistics>>;
};

/** Managed Manual Repeat: one Site waiting for the operator's Continue. */
export type AwaitingContinueSite = {
  ppu_id: string;
  site_id: number;
  continue_seq: number;
  /** Why it waits, plus the system's own FAIL evidence when a Cycle failed. */
  detail: string;
};

export type ServerBatchSnapshot = {
  /** Manual Repeat: Sites waiting for the operator's Continue. */
  awaiting_continue?: AwaitingContinueSite[];
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
  read: { scope: "main_flash" } | { offset: number; length: number };
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
};

export const terminalServerBatchStates = new Set<ServerBatchState>([
  "success",
  "partial",
  "error",
  "cancelled",
]);
