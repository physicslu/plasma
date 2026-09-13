import { useSyncExternalStore } from "react";

export type BatchSummaryLiveScope = "production" | "engineering";

export type BatchSummaryLiveMetrics = {
  sites: number;
  processedIc: number;
  totalIc: number;
};

const snapshots: Record<BatchSummaryLiveScope, BatchSummaryLiveMetrics | null> = {
  production: null,
  engineering: null,
};

const listeners: Record<BatchSummaryLiveScope, Set<() => void>> = {
  production: new Set(),
  engineering: new Set(),
};

function equalMetrics(left: BatchSummaryLiveMetrics | null, right: BatchSummaryLiveMetrics | null): boolean {
  if (left === right) return true;
  if (!left || !right) return false;
  return left.sites === right.sites
    && left.processedIc === right.processedIc
    && left.totalIc === right.totalIc;
}

export function batchSummaryScopeFromAriaLabel(ariaLabel: string): BatchSummaryLiveScope | null {
  if (ariaLabel === "Production Batch Summary") return "production";
  if (ariaLabel === "Engineering Batch Summary") return "engineering";
  return null;
}

export function publishBatchSummaryLiveMetrics(
  scope: BatchSummaryLiveScope,
  metrics: BatchSummaryLiveMetrics,
): void {
  if (equalMetrics(snapshots[scope], metrics)) return;
  snapshots[scope] = metrics;
  listeners[scope].forEach(listener => listener());
}

export function clearBatchSummaryLiveMetrics(scope: BatchSummaryLiveScope): void {
  if (snapshots[scope] === null) return;
  snapshots[scope] = null;
  listeners[scope].forEach(listener => listener());
}

export function useBatchSummaryLiveMetrics(
  scope: BatchSummaryLiveScope,
): BatchSummaryLiveMetrics | null {
  return useSyncExternalStore(
    listener => {
      listeners[scope].add(listener);
      return () => listeners[scope].delete(listener);
    },
    () => snapshots[scope],
    () => null,
  );
}
