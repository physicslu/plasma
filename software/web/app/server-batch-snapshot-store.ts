import type { ServerBatchSnapshot } from "./server-batch-api";

let latestSnapshot: ServerBatchSnapshot | null = null;
const listeners = new Set<() => void>();

export function publishServerBatchSnapshot(snapshot: ServerBatchSnapshot): void {
  latestSnapshot = snapshot;
  for (const listener of listeners) listener();
}

export function getServerBatchSnapshot(): ServerBatchSnapshot | null {
  return latestSnapshot;
}

export function getServerBatchServerSnapshot(): ServerBatchSnapshot | null {
  return null;
}

export function subscribeServerBatchSnapshot(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
