type Listener = () => void;

const listeners = new Set<Listener>();
let activeBatchExecutions = 0;

// Keep this key aligned with the Production page reconnect hint. The storage
// check is deliberately inside the activity store so a temporary Batch polling
// failure cannot unlock P/E mode switching while the authoritative server
// Batch may still be running.
const ACTIVE_BATCH_STORAGE_KEY = "plasma-production-active-batch-v1";

function hasUnresolvedStoredBatch(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Boolean(window.sessionStorage.getItem(ACTIVE_BATCH_STORAGE_KEY));
  } catch {
    return false;
  }
}

function emit(): void {
  listeners.forEach(listener => listener());
}

export function subscribeBatchExecutionActivity(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// sessionStorage does not dispatch a storage event in the same document that
// changes it. Lease writers must explicitly wake the global navigation store.
export function notifyBatchExecutionActivityChanged(): void {
  emit();
}

export function getBatchExecutionActivityCount(): number {
  // A stored non-terminal Batch ID is a fail-closed execution lease. During
  // normal observation activeBatchExecutions is already 1, so max() avoids
  // double-counting. If observation drops and the component releases its local
  // lease, the stored Batch keeps navigation locked until reconnect/terminal.
  return Math.max(activeBatchExecutions, hasUnresolvedStoredBatch() ? 1 : 0);
}

export function beginBatchExecutionActivity(): () => void {
  activeBatchExecutions += 1;
  emit();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    activeBatchExecutions = Math.max(0, activeBatchExecutions - 1);
    emit();
  };
}
