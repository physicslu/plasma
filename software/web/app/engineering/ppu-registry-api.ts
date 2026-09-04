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

export type PPUSiteDesired = {
  enabled: boolean;
  interface: string;
  target: string;
};

export type PPUSiteActual = {
  enabled: boolean;
  interface: string | null;
  target: string | null;
  state: string | null;
  current_job_id: string | null;
};

export type PPUSiteReconciliation =
  | "in_sync"
  | "restart_required"
  | "actual_unavailable"
  | "disabled_runtime_binding_unobservable";

export type PPUSiteConfigurationView = {
  site_id: number;
  desired: PPUSiteDesired;
  actual: PPUSiteActual | null;
  reconciliation: PPUSiteReconciliation;
};

export type PPUSiteConfigurationPayload = {
  ok: true;
  rest_contract_version: string;
  site_configuration: {
    source: "canonical_ppu_config";
    runtime_apply_supported: false;
    reconciliation: "in_sync" | "restart_required" | "actual_unavailable" | "partially_observable";
    sites: PPUSiteConfigurationView[];
  };
};

export type ManagerNetworkCommissioningState =
  | "requested"
  | "desired_saved"
  | "apply_requested"
  | "reconnecting"
  | "identity_verified"
  | "activation_committed"
  | "registry_reconciled"
  | "rollback_wait"
  | "completed"
  | "rolled_back"
  | "failed"
  | "recovery_required";

export type ManagerNetworkCommissioning = {
  transaction_id: string;
  request_key: string;
  request_fingerprint: string;
  alias: string;
  state: ManagerNetworkCommissioningState;
  old_endpoint: string;
  candidate_endpoint: string | null;
  ppu_id: string | null;
  desired_revision: number | null;
  activation_id: string | null;
  rollback_timeout_s: number;
  rollback_deadline_epoch_s: number | null;
  started_at: string;
  updated_at: string;
  error_code: string | null;
  error_message: string | null;
};

export type ManagerNetworkCommissioningPayload = {
  ok: true;
  commissioning: ManagerNetworkCommissioning;
  registry?: ManagerRegistryPayload;
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
    error_code?: number;
    error_type?: string;
    message?: string;
  };
};

function requestError(status: number, payload: ErrorPayload | null): Error {
  const message = payload?.error?.message ?? `Request failed with HTTP ${status}`;
  const code = payload?.error?.code ?? payload?.error?.error_type;
  return new Error(code ? `${code}: ${message}` : message);
}

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
  if (!response.ok || payload == null) throw requestError(response.status, payload);
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

export function getManagerPpuSites(alias: string): Promise<PPUSiteConfigurationPayload> {
  return jsonRequest<PPUSiteConfigurationPayload>(`/api/manager/registry/${encodeURIComponent(alias)}/sites`);
}

export function saveManagerPpuSite(
  alias: string,
  siteId: number,
  desired: PPUSiteDesired,
): Promise<PPUSiteConfigurationPayload> {
  if (!Number.isInteger(siteId) || siteId < 1) {
    return Promise.reject(new Error("Site ID must be a positive 1-based integer"));
  }
  return jsonRequest<PPUSiteConfigurationPayload>(
    `/api/manager/registry/${encodeURIComponent(alias)}/sites/${siteId}`,
    {
      method: "POST",
      headers: {
        "Idempotency-Key": `site-desired-${siteId}-${crypto.randomUUID()}`,
      },
      body: JSON.stringify(desired),
    },
  );
}

export async function getManagerPpuNetworkCommissioning(
  alias: string,
): Promise<ManagerNetworkCommissioning | null> {
  const response = await fetch(
    `/api/manager/registry/${encodeURIComponent(alias)}/network-commissioning`,
    { cache: "no-store", headers: { Accept: "application/json" } },
  );
  if (response.status === 404) return null;
  const payload = await response.json().catch(() => null) as (ManagerNetworkCommissioningPayload & ErrorPayload) | null;
  if (!response.ok || payload == null) throw requestError(response.status, payload);
  return payload.commissioning;
}

export function commissionManagerPpuStaticNetwork(
  alias: string,
  settings: PPUNetworkDesiredInput,
  rollbackTimeoutSeconds = 20,
): Promise<ManagerNetworkCommissioningPayload> {
  return jsonRequest<ManagerNetworkCommissioningPayload>(
    `/api/manager/registry/${encodeURIComponent(alias)}/network-commissioning`,
    {
      method: "POST",
      headers: {
        "Idempotency-Key": `ppu-network-commissioning-${crypto.randomUUID()}`,
      },
      body: JSON.stringify({
        desired: settings,
        rollback_timeout_s: rollbackTimeoutSeconds,
      }),
    },
  );
}
