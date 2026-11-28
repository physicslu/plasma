type Listener = () => void;

const listeners = new Set<Listener>();
let activeBatchExecutions = 0;

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
  // Manager-owned Batches: the observer holds this lease while a Batch is
  // non-terminal. The Manager Batch ID kept in sessionStorage is a read-only
  // observation key that outlives a terminal Batch, so it is not a lease.
  return activeBatchExecutions;
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
