import { useSyncExternalStore } from "react";

export type BatchSummaryLiveChannel = "production" | "engineering";

export type BatchSummaryLiveMetrics = {
  sites: number;
  processedIc: number;
  totalIc: number;
};

const snapshots: Record<BatchSummaryLiveChannel, BatchSummaryLiveMetrics | null> = {
  production: null,
  engineering: null,
};

const listeners: Record<BatchSummaryLiveChannel, Set<() => void>> = {
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

export function batchSummaryChannelFromAriaLabel(ariaLabel: string): BatchSummaryLiveChannel | null {
  if (ariaLabel === "Production Batch Summary") return "production";
  if (ariaLabel === "Engineering Batch Summary") return "engineering";
  return null;
}

export function publishBatchSummaryLiveMetrics(
  channel: BatchSummaryLiveChannel,
  metrics: BatchSummaryLiveMetrics,
): void {
  if (equalMetrics(snapshots[channel], metrics)) return;
  snapshots[channel] = metrics;
  listeners[channel].forEach(listener => listener());
}

export function clearBatchSummaryLiveMetrics(channel: BatchSummaryLiveChannel): void {
  if (snapshots[channel] === null) return;
  snapshots[channel] = null;
  listeners[channel].forEach(listener => listener());
}

export function useBatchSummaryLiveMetrics(
  channel: BatchSummaryLiveChannel,
): BatchSummaryLiveMetrics | null {
  return useSyncExternalStore(
    listener => {
      listeners[channel].add(listener);
      return () => listeners[channel].delete(listener);
    },
    () => snapshots[channel],
    () => null,
  );
}
