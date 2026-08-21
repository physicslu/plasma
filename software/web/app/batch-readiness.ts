export type BatchReadinessCode =
  | "batch-ready"
  | "no-target"
  | "no-site"
  | "no-op"
  | "image-required"
  | "image-invalid"
  | "invalid-read"
  | "ppu-offline"
  | "site-busy"
  | "running"
  | "cancelling";

export type BatchReadinessInput = {
  providerOnline: boolean;
  targetValid: boolean;
  selectedSiteCount: number;
  selectedOperationCount: number;
  requiresImage: boolean;
  imagePresent: boolean;
  imageValid: boolean;
  readSelected: boolean;
  readParamsValid: boolean;
  allSitesExecutable: boolean;
  batchRunning: boolean;
  batchCancelling: boolean;
};

export type BatchReadiness = {
  code: BatchReadinessCode;
  label: string;
  ready: boolean;
};

const LABELS: Record<BatchReadinessCode, string> = {
  "batch-ready": "BATCH READY",
  "no-target": "NO TARGET",
  "no-site": "NO SITE",
  "no-op": "NO OP",
  "image-required": "IMAGE REQUIRED",
  "image-invalid": "IMAGE INVALID",
  "invalid-read": "INVALID READ",
  "ppu-offline": "PPU OFFLINE",
  "site-busy": "SITE BUSY",
  running: "RUNNING",
  cancelling: "CANCELLING",
};

function result(code: BatchReadinessCode): BatchReadiness {
  return { code, label: LABELS[code], ready: code === "batch-ready" };
}

/**
 * Single source of truth for Pmod/Emode batch dispatch readiness.
 * The status badge and Execute button must consume this same result.
 */
export function evaluateBatchReadiness(input: BatchReadinessInput): BatchReadiness {
  if (input.batchCancelling) return result("cancelling");
  if (input.batchRunning) return result("running");
  if (!input.providerOnline) return result("ppu-offline");
  if (!input.targetValid) return result("no-target");
  if (input.selectedSiteCount <= 0) return result("no-site");
  if (input.selectedOperationCount <= 0) return result("no-op");
  if (input.requiresImage && !input.imagePresent) return result("image-required");
  if (input.requiresImage && !input.imageValid) return result("image-invalid");
  if (input.readSelected && !input.readParamsValid) return result("invalid-read");
  if (!input.allSitesExecutable) return result("site-busy");
  return result("batch-ready");
}
