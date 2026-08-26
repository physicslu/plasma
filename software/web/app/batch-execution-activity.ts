type Listener = () => void;

const listeners = new Set<Listener>();
let activeBatchExecutions = 0;

// Keep these keys aligned with the PMode and EMode server-Batch reconnect
// handles. Storage checks deliberately live in the shared activity store so a
// temporary observer loss or a mode-local component unmount cannot unlock
// P/E mode switching while an authoritative server Batch may still be active.
const ACTIVE_BATCH_STORAGE_KEYS = [
  "plasma-production-active-batch-v1",
  "plasma-engineering-active-batch-v1",
] as const;

function hasUnresolvedStoredBatch(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return ACTIVE_BATCH_STORAGE_KEYS.some(key => Boolean(window.sessionStorage.getItem(key)));
  } catch {
    return false;
  }
}

function emit(): void {
  listeners.forEach(listener => listener());
}

export function subscribeBatchExecutionActivity(listener: () => void): () => void {
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
  // double-counting. If observation drops or a mode-local surface unmounts,
  // the stored Batch keeps navigation locked until reconnect/terminal.
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
