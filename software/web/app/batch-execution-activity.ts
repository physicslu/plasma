type Listener = () => void;

const listeners = new Set<Listener>();
let activeBatchExecutions = 0;

function emit(): void {
  listeners.forEach(listener => listener());
}

export function subscribeBatchExecutionActivity(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getBatchExecutionActivityCount(): number {
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
