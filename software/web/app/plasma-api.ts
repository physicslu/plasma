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

export type AssetTransferEvent = ProgrammingAssetFingerprint & {
  kind: "cache_check" | "cache_hit" | "cache_miss" | "upload_start" | "upload_complete";
};

export type JobTargetDeviceRequest = {
  vendor: string;
  identifier: string;
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
