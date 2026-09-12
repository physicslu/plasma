import {
  getManagerPpuSites,
  ManagerApiError,
  type PPUSiteConfigurationPayload,
} from "./ppu-registry-api";

export type RuntimeActivationCapability =
  | {
      supported: true;
      payload: PPUSiteConfigurationPayload;
    }
  | {
      supported: false;
      payload: PPUSiteConfigurationPayload | null;
      reason: "site-settings-route-unavailable" | "runtime-apply-disabled";
    };

export function isMissingRuntimeCapabilityRoute(error: unknown): boolean {
  return error instanceof ManagerApiError
    && error.status === 404
    && error.code === null
    && error.message === "not found";
}

export async function getRuntimeActivationCapability(alias: string): Promise<RuntimeActivationCapability> {
  try {
    const payload = await getManagerPpuSites(alias);
    if (!payload.site_configuration.runtime_apply_supported) {
      return {
        supported: false,
        payload,
        reason: "runtime-apply-disabled",
      };
    }
    return { supported: true, payload };
  } catch (error) {
    if (isMissingRuntimeCapabilityRoute(error)) {
      return {
        supported: false,
        payload: null,
        reason: "site-settings-route-unavailable",
      };
    }
    throw error;
  }
}
