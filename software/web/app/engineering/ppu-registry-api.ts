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

type ErrorPayload = {
  error?: {
    code?: string;
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
    const code = payload?.error?.code;
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

export function addManagerPpu(alias: string, endpoint: string): Promise<{ ok: true; entry: ManagerRegistryEntry; registry: ManagerRegistryPayload }> {
  return jsonRequest("/api/manager/registry", {
    method: "POST",
    body: JSON.stringify({ alias, endpoint }),
  });
}

export function setManagerPpuLifecycle(
  alias: string,
  lifecycle: Exclude<RegistryLifecycle, "pending">,
): Promise<{ ok: true; entry: ManagerRegistryEntry; registry: ManagerRegistryPayload }> {
  return jsonRequest(`/api/manager/registry/${encodeURIComponent(alias)}`, {
    method: "PATCH",
    body: JSON.stringify({ lifecycle }),
  });
}

export function removeManagerPpu(alias: string): Promise<{ ok: true; removed: ManagerRegistryEntry; registry: ManagerRegistryPayload }> {
  return jsonRequest(`/api/manager/registry/${encodeURIComponent(alias)}`, {
    method: "DELETE",
  });
}
