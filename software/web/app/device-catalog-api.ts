import { DEFAULT_API_BASE, normalizeApiBase } from "./plasma-api";

export type DeviceIdentifierKind =
  | "manufacturer_part_number"
  | "cmsis_device_name"
  | "ordering_pattern"
  | "family_alias"
  | string;

export type DeviceSearchResult = {
  vendor: string;
  family: string;
  subfamily: string | null;
  plasma_series: string;
  identifier: string;
  identifier_kind: DeviceIdentifierKind;
  icpn: string | null;
  package: string | null;
  cpu_architectures: string[];
  backend: {
    type: string;
    distribution: string;
    target_config: string;
    mapping_status: string;
  };
  physical_validation: {
    engineering_status: string;
    ppu_status: string;
    socket_status: string;
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

export function configuredDeviceApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  const saved = window.localStorage.getItem("plasma-api-base");
  if (!saved) return DEFAULT_API_BASE;
  try {
    return normalizeApiBase(saved);
  } catch {
    return DEFAULT_API_BASE;
  }
}

export async function searchDevices(
  query: string,
  options: { apiBase?: string; limit?: number; signal?: AbortSignal } = {},
): Promise<DeviceSearchResponse> {
  const apiBase = normalizeApiBase(options.apiBase ?? configuredDeviceApiBase());
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
