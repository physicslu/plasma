import type { DeviceSearchResult } from "./device-catalog-api";
import type { Operation } from "./plasma-api";
import type {
  BatchExecutionPolicy,
  BatchTargetDeviceSnapshot,
  BatchTargetRequest,
  CreateServerBatchOptions,
  ServerBatchSnapshot,
} from "./server-batch-api";

export const DEFAULT_PRODUCTION_SITE_RETRY_LIMIT = 3;

export type ProductionStopPolicy =
  | { kind: "never" }
  | { kind: "failed_sites"; threshold: number };

export type ProductionProgrammingJobDraft = {
  facilityId: string;
  ppuId: string;
  siteIds: number[];
  targetDevice: DeviceSearchResult | null;
  programmingImage: File | null;
  operations: Operation[];
  repeatCount: number;
  stopPolicy: ProductionStopPolicy;
};

export type ProductionManufacturingKpis = {
  totalIc: number;
  pass: number;
  fail: number;
  yieldPercent: number;
  runningSites: number;
};

export function targetDeviceLabel(device: DeviceSearchResult | null): string {
  if (!device) return "—";
  return device.icpn ?? device.identifier;
}

export function batchTargetDeviceLabel(device: BatchTargetDeviceSnapshot | null | undefined): string {
  if (!device) return "—";
  return device.icpn ?? device.identifier;
}

export function productionPolicy(
  repeatCount: number,
  stopPolicy: ProductionStopPolicy,
): BatchExecutionPolicy {
  return {
    repeat_count: repeatCount,
    site_retry_limit: DEFAULT_PRODUCTION_SITE_RETRY_LIMIT,
    failed_site_stop_threshold: stopPolicy.kind === "failed_sites" ? stopPolicy.threshold : null,
  };
}

export function singlePpuBatchTargets(
  facilityId: string,
  ppuId: string,
  siteIds: number[],
): BatchTargetRequest[] {
  return [{
    facility_id: facilityId,
    ppu_id: ppuId,
    site_ids: [...siteIds].sort((a, b) => a - b),
  }];
}

export function buildServerBatchOptions(
  draft: ProductionProgrammingJobDraft,
  sessionId: string | null,
): CreateServerBatchOptions {
  return {
    sessionId,
    targets: singlePpuBatchTargets(draft.facilityId, draft.ppuId, draft.siteIds),
    operations: draft.operations,
    executionPolicy: productionPolicy(draft.repeatCount, draft.stopPolicy),
    targetDevice: draft.targetDevice
      ? { vendor: draft.targetDevice.vendor, identifier: draft.targetDevice.identifier }
      : null,
    assetFile: draft.programmingImage,
    allowSyntheticMockImage: false,
  };
}

export function manufacturingKpis(
  batch: ServerBatchSnapshot | null,
  idleSelectedSiteCount = 0,
): ProductionManufacturingKpis {
  if (!batch) {
    return {
      totalIc: idleSelectedSiteCount,
      pass: 0,
      fail: 0,
      yieldPercent: 0,
      runningSites: 0,
    };
  }
  const pass = batch.sites.reduce((total, site) => total + Math.max(0, site.completed_rounds), 0);
  const fail = batch.sites.reduce((total, site) => total + Math.max(0, site.final_failures), 0);
  const totalIc = pass + fail;
  return {
    totalIc,
    pass,
    fail,
    yieldPercent: totalIc > 0 ? (pass / totalIc) * 100 : 0,
    runningSites: batch.site_counts.running ?? 0,
  };
}

export function validateProgrammingDraft(draft: ProductionProgrammingJobDraft): string | null {
  if (!draft.facilityId || !draft.ppuId) return "Select a Facility and PPU.";
  if (draft.siteIds.length === 0) return "Select at least one Site.";
  if (!draft.targetDevice) return "Select a Target IC.";
  if (draft.operations.length === 0) return "Select at least one E/P/V/R operation.";
  if (!Number.isInteger(draft.repeatCount) || draft.repeatCount < 1 || draft.repeatCount > 10_000) {
    return "Repeat must be an integer between 1 and 10000.";
  }
  if (
    draft.stopPolicy.kind === "failed_sites"
    && (!Number.isInteger(draft.stopPolicy.threshold)
      || draft.stopPolicy.threshold < 1
      || draft.stopPolicy.threshold > draft.siteIds.length)
  ) {
    return "Stop Policy threshold must not exceed the selected Site count.";
  }
  const requiresImage = draft.operations.some(operation => operation === "program" || operation === "verify");
  if (requiresImage && !draft.programmingImage) return "Program / Verify requires a Programming Image.";
  return null;
}
