export type BatchReadinessCode =
  | "batch-ready"
  | "no-target"
  | "no-site"
  | "no-op"
  | "image-required"
  | "image-invalid"
  | "invalid-read"
  | "programming-unavailable"
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

export type BatchReadinessLocale = "zh-TW" | "en-US";

const LABELS: Record<BatchReadinessCode, string> = {
  "batch-ready": "BATCH READY",
  "no-target": "NO TARGET",
  "no-site": "NO SITE",
  "no-op": "NO OP",
  "image-required": "IMAGE REQUIRED",
  "image-invalid": "IMAGE INVALID",
  "invalid-read": "INVALID READ",
  "programming-unavailable": "PROGRAMMING UNAVAILABLE",
  "site-busy": "SITE BUSY",
  running: "RUNNING",
  cancelling: "CANCELLING",
};

const GUIDANCE: Record<BatchReadinessCode, Record<BatchReadinessLocale, string>> = {
  "batch-ready": {
    "zh-TW": "可以開始燒錄。",
    "en-US": "Ready to start programming.",
  },
  "no-target": {
    "zh-TW": "請先選擇目標 IC。",
    "en-US": "Select a target IC first.",
  },
  "no-site": {
    "zh-TW": "請至少勾選一個 Site。",
    "en-US": "Select at least one Site.",
  },
  "no-op": {
    "zh-TW": "請選擇 Erase / Program / Verify / Read。",
    "en-US": "Select Erase / Program / Verify / Read.",
  },
  "image-required": {
    "zh-TW": "Program／Verify 需要 Programming Image。",
    "en-US": "Program / Verify requires a Programming Image.",
  },
  "image-invalid": {
    "zh-TW": "Programming Image 無效，請重新選擇或上傳。",
    "en-US": "The Programming Image is invalid. Select or upload it again.",
  },
  "invalid-read": {
    "zh-TW": "Read 參數不完整。",
    "en-US": "Complete the Read parameters.",
  },
  "programming-unavailable": {
    "zh-TW": "燒錄功能目前不可用；請檢查 Programming Provider。",
    "en-US": "Programming is unavailable. Check the Programming Provider.",
  },
  "site-busy": {
    "zh-TW": "有 Site 忙碌中；請等待完成或取消目前 Batch。",
    "en-US": "One or more Sites are busy. Wait for completion or cancel the active Batch.",
  },
  running: {
    "zh-TW": "Batch 執行中；Site membership 已鎖定。",
    "en-US": "Batch execution is in progress; Site membership is locked.",
  },
  cancelling: {
    "zh-TW": "Batch 取消中；請等待 Server 回報終止狀態。",
    "en-US": "Batch cancellation is in progress. Wait for the Server terminal state.",
  },
};

function result(code: BatchReadinessCode): BatchReadiness {
  return { code, label: LABELS[code], ready: code === "batch-ready" };
}

export function batchReadinessGuidance(code: BatchReadinessCode, locale: BatchReadinessLocale): string {
  return GUIDANCE[code][locale];
}

export function batchReadinessGuidanceFromLabel(label: string, locale: BatchReadinessLocale): string | null {
  const entry = (Object.entries(LABELS) as Array<[BatchReadinessCode, string]>).find(([, value]) => value === label);
  return entry ? batchReadinessGuidance(entry[0], locale) : null;
}

/**
 * Single source of truth for Pmod/Emode batch dispatch readiness.
 * The status badge and Execute button must consume this same result.
 *
 * Provider availability is a Programming capability signal, not a PPU
 * connectivity signal. Gateway/PPU reachability is reported independently by
 * the communication-health model; a missing Programming provider must never be
 * presented to the operator as "PPU OFFLINE".
 */
export function evaluateBatchReadiness(input: BatchReadinessInput): BatchReadiness {
  if (input.batchCancelling) return result("cancelling");
  if (input.batchRunning) return result("running");
  if (!input.providerOnline) return result("programming-unavailable");
  if (!input.targetValid) return result("no-target");
  if (input.selectedSiteCount <= 0) return result("no-site");
  if (input.selectedOperationCount <= 0) return result("no-op");
  if (input.requiresImage && !input.imagePresent) return result("image-required");
  if (input.requiresImage && !input.imageValid) return result("image-invalid");
  if (input.readSelected && !input.readParamsValid) return result("invalid-read");
  if (!input.allSitesExecutable) return result("site-busy");
  return result("batch-ready");
}
