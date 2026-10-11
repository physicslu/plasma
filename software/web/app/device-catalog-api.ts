import { normalizeApiBase } from "./plasma-api";

export type BackendCandidateEvidence = {
  family: "STM32H5" | "STM32C5";
  status: "research_only";
  production_mapping_status: "no_mapping";
  provider_id: string;
  source_repository: string;
  source_commit: string;
  target_config_source_path: string;
  target_config_git_blob: string;
  flash_driver: string;
  flash_driver_source_path: string;
  flash_driver_git_blob: string;
  expected_device_id: string;
  device_id_evidence: string;
  catalog_flash_kib: number;
  driver_max_flash_kib: number;
  flash_size_readback_kib: null;
  sector_size_kib_source_only: number | null;
  write_alignment_bytes_source_only: number | null;
  loader_source_path: string | null;
  loader_sha256: string | null;
  dfp_exact_variant_status: "exact" | "base_device_only" | null;
  dfp_source_commit?: string;
  dfp_declared_algorithm_ram_bytes?: number;
  fork_default_workarea_bytes?: number;
  loader_installed?: false;
  loader_qualified?: false;
  executable: false;
  production_binding_authorized: false;
  hardware_runtime_ready: false;
  physical_programming_qualified: false;
  blockers: string[];
};

export type BackendSourceReference = {
  provider_id: string;
  provider_name: string;
  mapping_status: "mapped" | "candidate";
  target_config: string;
  flash_driver: string | null;
  source_repository: string | null;
  source_version: string | null;
  source_commit: string | null;
  pinned_release_runtime_id: string | null;
  installed_runtime_id: string | null;
  installed_binary_sha256: string | null;
  evidence_scope: "catalog_mapping_only" | "source_pinned_research_only";
  hardware_runtime_ready: false;
  physical_programming_qualified: false;
};

export type BackendSoftwareBuildEvidence = {
  architecture: string;
  environment: string;
  runtime_id: string;
  artifact_sha256: string;
  payload_sha256: string;
  binary_sha256: null;
  github_actions_run_id: number;
  qualification: string;
  scope: string;
  published_binary: false;
};

export type VersionedOpenOCDProvider = {
  provider_id: string;
  provider_distribution: string;
  source_repository: string;
  source_commit: string;
  source_version: string | null;
  declared_release_runtime_id: string | null;
  target_config: string;
  flash_driver: string | null;
  mapping_status: "mapped" | "candidate";
  software_build_evidence: BackendSoftwareBuildEvidence[];
  installed_runtime_id: null;
  installed_binary_sha256: null;
  site_id: null;
  software_process_capability: "metadata_description_only";
  qualified_hardware_operations: [];
  hardware_runtime_ready: false;
  real_ic_erase_program_verify: false;
  production_write_authorized: false;
  executable: false;
  source_evidence_only: true;
};

export type DeviceIdentifierKind = "manufacturer_part_number" | string;

export type DeviceSearchResult = {
  vendor: string;
  family: string;
  subfamily: string | null;
  plasma_series: string;
  identifier: string;
  identifier_kind: DeviceIdentifierKind;
  icpn: string | null;
  package: string | null;
  pin_count: string | null;
  flash_size: string | null;
  temperature_grade: string | null;
  option_suffix: string | null;
  base_device: string | null;
  cpu_architectures: string[];
  backend: {
    type: string;
    distribution: string;
    target_config: string;
    mapping_status: string;
    mapping_method: string | null;
  };
  catalog_verification: {
    status: string | null;
    source_type: string | null;
    source_authority: string | null;
    source_reference: string | null;
  };
  physical_validation: {
    engineering_status: string;
    ppu_status: string;
    socket_status: string;
  };
  catalog: {
    scope: string;
    version: string | null;
    revision_sha256: string | null;
  };
  catalog_origin: string;
  backend_candidate?: BackendCandidateEvidence | null;
  backend_source_reference?: BackendSourceReference | null;
  backend_providers?: VersionedOpenOCDProvider[];
};

export type DeviceSearchResponse = {
  ok: boolean;
  rest_contract_version?: string;
  query: string;
  catalog_size: number;
  count: number;
  results: DeviceSearchResult[];
};

export type DeviceSearchOptions = {
  apiBase: string;
  limit?: number;
  signal?: AbortSignal;
};

export async function searchDevices(
  query: string,
  options: DeviceSearchOptions,
): Promise<DeviceSearchResponse> {
  const apiBase = normalizeApiBase(options.apiBase);
  const limit = options.limit ?? 20;
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const response = await fetch(`${apiBase}/api/devices/search?${params.toString()}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  const payload = (await response.json()) as DeviceSearchResponse & {
    error?: { message?: string };
  };
  if (!response.ok) {
    throw new Error(payload.error?.message ?? `Device search HTTP ${response.status}`);
  }
  return payload;
}
