import { normalizeApiBase } from "./plasma-api";

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
