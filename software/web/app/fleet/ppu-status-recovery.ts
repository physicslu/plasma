import type { EngineeringTargetCatalog, PPUStatus } from "../plasma-api";
import { engineeringTargetApiBase, getPPUStatus } from "../plasma-api";
import type { SelectionMap } from "../workspace-session";

export const PPU_STATUS_RETRY_DELAYS_MS = [1_000, 2_000, 4_000, 5_000] as const;
export const PPU_STATUS_REQUEST_TIMEOUT_MS = 5_000;

export type RecoverablePPUTarget = {
  facilityId: string;
  ppuId: string;
  siteIds: number[];
};

export function selectedPPUTargets(
  catalog: EngineeringTargetCatalog,
  selection: SelectionMap,
): RecoverablePPUTarget[] {
  return catalog.facilities.flatMap(facility => facility.ppus.flatMap(ppu => {
    const siteIds = selection[facility.facility_id]?.[ppu.ppu_id] ?? [];
    return siteIds.length
      ? [{ facilityId: facility.facility_id, ppuId: ppu.ppu_id, siteIds: [...siteIds] }]
      : [];
  }));
}

export async function probePPUStatus(
  apiBase: string,
  target: RecoverablePPUTarget,
): Promise<PPUStatus> {
  return await getPPUStatus(
    engineeringTargetApiBase(apiBase, target.facilityId, target.ppuId),
    PPU_STATUS_REQUEST_TIMEOUT_MS,
  );
}

export function ppuRetryDelayMs(failureCount: number): number {
  const index = Math.max(0, Math.min(failureCount - 1, PPU_STATUS_RETRY_DELAYS_MS.length - 1));
  return PPU_STATUS_RETRY_DELAYS_MS[index];
}
