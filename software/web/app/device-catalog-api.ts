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

export type SelectedICProfile = {
  schema_version: "1.0.0";
  status: "manufacturer_profile_available";
  icpn: string;
  manufacturer_baseline: {
    baseline_id: string;
    status: "frozen_manufacturer_only";
    sha256: string;
    authority: "manufacturer_official_only";
    sources: Array<{
      source_id: string;
      document_number?: string;
      revision?: string;
      sha256?: string;
      used_for?: string[];
    }>;
  };
  catalog_identity: {
    base_device: string;
    package: string;
    pin_count: number | string;
    flash_size: string;
  };
  device: {
    identity: {
      cpu_core?: string;
      cpu_max_frequency_hz?: number;
      package?: string;
      pin_count?: number;
      temperature_grade?: string;
      ambient_temperature_c?: { min: number; max: number };
    };
    operating_electrical: {
      vdd_v: { min: number; max: number };
      io_supply_v?: { min: number; max: number };
      vdda_v?: { min: number; max: number };
      vdda_min_when_adc_used_v?: number;
      absolute_maximum_values_are_not_setpoints?: boolean;
    };
    memory_map: {
      main_flash: {
        start: string;
        end: string;
        size_bytes: number;
        page_size_bytes: number;
        page_count: number;
      };
      sram?: { start: string; end: string; size_bytes: number };
      system_memory?: { start: string; end: string; size_bytes: number };
      option_bytes?: { start: string; end: string; size_bytes: number };
    };
  };
  programming: {
    interfaces: Record<string, {
      clock_hz?: {
        manufacturer_min: number | null;
        manufacturer_max: number | null;
        manufacturer_recommended: number | null;
        status: string;
      };
      status?: string;
      boot_source?: string;
      transport_detail?: string;
      required_signal_pins?: Array<{ signal: string; mcu_pin: string; io_level?: string }>;
      recommended_support_signals?: string[];
      special_requirements?: string[];
    }>;
    electrical: {
      vdd_programming_v: { min: number; max: number; basis?: string };
      recommended_vdd_v?: { status: string; value: number | null };
      external_vpp?: { required: boolean; basis?: string };
      io_reference?: string;
      programmer_current_limit?: { status: string; value: number | null };
      programming_specific_power_sequence?: { status: string };
    };
    flash_geometry: {
      erase_unit: string;
      erase_unit_bytes: number;
      program_unit: string;
      program_unit_bytes: number;
      program_alignment_bytes: number;
      mass_erase_supported: boolean;
      verify_by_readback: boolean;
    };
    flash_controller: Record<string, unknown>;
    special_constraints: Array<{ id: string; effect: string; recovery?: string }>;
    program_model: {
      normal_write_flow: string[];
      not_yet_modeled: string[];
      operations: Record<string, Array<Record<string, unknown>>>;
    };
  };
  plasma_compatibility: {
    site_electrical_compatibility: "not_evaluated";
    socket_compatibility: "not_evaluated";
    hardware_runtime_ready: false;
    physical_programming_qualified: false;
  };
  ic_support: {
    binding_set_id: string;
    binding_status: string;
    profiles: Record<string, { profile_id: string; kind: string; status: string }>;
  };
};

export type ManufacturerDeviceBasicProfile = {
  schema_version: "1.0.0";
  status: "manufacturer_device_basic_available";
  profile_id: string;
  icpn: string;
  manufacturer: "STMicroelectronics";
  family: string;
  series: string;
  base_device: string;
  package: string;
  pin_count: string;
  flash_size: string;
  ram_size: string;
  operating_vdd_v: { min: number; max: number };
  io_supply_v: { min: number; max: number } | null;
  vdda_v: { min: number; max: number } | null;
  operating_temperature_c: { min: number; max: number };
  evidence: {
    authority: "STMicroelectronics official";
    source_surface: "st_product_selector" | "st_estore";
    selector_url: string;
    observed_at_utc: string;
    content_lock: null;
    evidence_strength: "official_product_selector_observation" | "official_estore_observation";
  };
  programming_profile_authority: false;
  hardware_runtime_ready: false;
  physical_programming_qualified: false;
};

export type NXPManufacturerDeviceProfile = {
  schema_version: "1.0.0";
  status: "manufacturer_device_partial_evidence";
  profile_id: "nxp-exact-manufacturer-device-v5";
  icpn: string;
  manufacturer: "NXP";
  family: "MCX" | "K32L2";
  base_device: string;
  base_device_evidence_state: "exact_sku_singleton_not_manufacturer_base_verified";
  package: string;
  pin_count: string;
  flash_size: string;
  ram_size: string;
  operating_vdd_v: { min: number; max: number } | null;
  io_supply_v: null;
  vdda_v: null;
  operating_temperature_c: { min: number; max: number };
  unknown_fields: Array<"io_supply" | "vdda" | "operating_vdd">;
  manufacturer_device_full_profile_complete: false;
  evidence: {
    authority: "NXP official";
    source_surface: "nxp_exact_part_html";
    exact_url: string;
    source_html_sha256: string;
    ram_evidence_state: string;
    vdd_evidence_state: string;
  };
  programming_profile_authority: false;
  hardware_runtime_ready: false;
  physical_programming_qualified: false;
};

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
  manufacturer_device_basic_profile?: ManufacturerDeviceBasicProfile | null;
  nxp_manufacturer_device_profile?: NXPManufacturerDeviceProfile | null;
  selected_profile?: SelectedICProfile | null;
};

export type DeviceSearchResponse = {
  ok: boolean;
  rest_contract_version?: string;
  query: string;
  catalog_size: number;
  count: number;
  total_count: number;
  limit: number;
  offset: number;
  results: DeviceSearchResult[];
};

export type DeviceSearchOptions = {
  apiBase: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

export async function searchDevices(
  query: string,
  options: DeviceSearchOptions,
): Promise<DeviceSearchResponse> {
  const apiBase = normalizeApiBase(options.apiBase);
  const limit = options.limit ?? 20;
  const offset = options.offset ?? 0;
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
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
