import { PlasmaApiError } from "../plasma-api";

export const PPU_STATUS_RETRY_DELAYS_MS = [1_000, 2_000, 4_000, 5_000] as const;
// Compatibility argument for FactoryConsoleV2. Engineering status observations
// resolve their HTTP watchdog from the canonical Gateway policy in plasma-api.
export const PPU_STATUS_REQUEST_TIMEOUT_MS = undefined;

export function isRecoverablePPUStatusError(error: unknown): boolean {
  return error instanceof PlasmaApiError && error.transient;
}

export function ppuRetryDelayMs(failureCount: number): number {
  const index = Math.max(0, Math.min(failureCount - 1, PPU_STATUS_RETRY_DELAYS_MS.length - 1));
  return PPU_STATUS_RETRY_DELAYS_MS[index];
}
