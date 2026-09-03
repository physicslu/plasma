import type { FleetWebPayload } from "../fleet/fleet-contract";

export type RegistryLifecycle = "pending" | "commissioned" | "disabled";

export type ManagerRegistryEntry = {
  endpoint: string;
  alias: string | null;
  lifecycle: RegistryLifecycle;
  registered_at: string;
  updated_at: string;
};

export type ManagerRegistryPayload = {
  ok: true;
  service: string;
  contract_version: string;
  mutable: boolean;
  storage: "file" | "config";
  ppus: ManagerRegistryEntry[];
};

export type PPUNetworkMode = "dhcp" | "static";

export type PPUNetworkSettings = {
  revision: number;
  interface: "eth0";
  mode: PPUNetworkMode;
  address: string | null;
  prefix_length: number | null;
  gateway: string | null;
  dns_servers: string[];
};

export type PPUNetworkActivation = {
  supported: boolean;
  state: string;
  activation_id?: string | null;
  revision?: number | null;
  ppu_id?: string | null;
  deadline_epoch_s?: number | null;
  committed_revision?: number | null;
  reason?: string | null;
  error?: string | null;
};

export type PPUNetworkPayload = {
  ok: true;
  rest_contract_version: string;
  ppu_network_settings: PPUNetworkSettings;
  activation: PPUNetworkActivation;
};

export type PPUNetworkDesiredInput = {
  mode: PPUNetworkMode;
  address: string | null;
  prefix_length: number | null;
  gateway: string | null;
  dns_servers: string[];
};

type RegistryMutationPayload = {
  ok: true;
  entry: ManagerRegistryEntry;
  registry: ManagerRegistryPayload;
};

type RegistryRemovePayload = {
  ok: true;
  removed: ManagerRegistryEntry;
  registry: ManagerRegistryPayload;
};

type ErrorPayload = {
  error?: {
    code?: string;
    error_type?: string;
    message?: string;
  };
};

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => null) as (T & ErrorPayload) | null;
  if (!response.ok || payload == null) {
    const message = payload?.error?.message ?? `Request failed with HTTP ${response.status}`;
    const code = payload?.error?.code ?? payload?.error?.error_type;
    throw new Error(code ? `${code}: ${message}` : message);
  }
  return payload;
}

export function getManagerRegistry(): Promise<ManagerRegistryPayload> {
  return jsonRequest<ManagerRegistryPayload>("/api/manager/registry");
}

export function getManagerFleet(): Promise<FleetWebPayload> {
  return jsonRequest<FleetWebPayload>("/api/fleet");
}

export function addManagerPpu(alias: string, endpoint: string): Promise<RegistryMutationPayload> {
  return jsonRequest<RegistryMutationPayload>("/api/manager/registry", {
    method: "POST",
    body: JSON.stringify({ alias, endpoint }),
  });
}

export function setManagerPpuLifecycle(
  alias: string,
  lifecycle: Exclude<RegistryLifecycle, "pending">,
): Promise<RegistryMutationPayload> {
  return jsonRequest<RegistryMutationPayload>(`/api/manager/registry/${encodeURIComponent(alias)}`, {
    method: "PATCH",
    body: JSON.stringify({ lifecycle }),
  });
}

export function removeManagerPpu(alias: string): Promise<RegistryRemovePayload> {
  return jsonRequest<RegistryRemovePayload>(`/api/manager/registry/${encodeURIComponent(alias)}`, {
    method: "DELETE",
  });
}

export function getManagerPpuNetwork(alias: string): Promise<PPUNetworkPayload> {
  return jsonRequest<PPUNetworkPayload>(`/api/manager/registry/${encodeURIComponent(alias)}/network`);
}

export function saveManagerPpuNetwork(
  alias: string,
  settings: PPUNetworkDesiredInput,
): Promise<PPUNetworkPayload> {
  return jsonRequest<PPUNetworkPayload>(`/api/manager/registry/${encodeURIComponent(alias)}/network`, {
    method: "POST",
    headers: {
      "Idempotency-Key": `ppu-network-desired-${crypto.randomUUID()}`,
    },
    body: JSON.stringify(settings),
  });
}
