export const MANAGER_CONTRACT_VERSION = "1" as const;

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

export function requireManagerContractVersion(value: unknown): void {
  const payload = object(value);
  const version = payload?.contract_version;
  if (version !== MANAGER_CONTRACT_VERSION) {
    throw new Error(`Unsupported Plasma Manager contract version: ${typeof version === "string" ? version : "missing"}`);
  }
}

export function requireManagerRegistryContractVersion(value: unknown): void {
  const payload = object(value);
  const registry = object(payload?.registry);
  requireManagerContractVersion(registry ?? payload);
}
