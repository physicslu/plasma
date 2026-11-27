import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

// Replaces the retired server-batch-activity contract (U10): every Batch is
// Manager-owned, so the P/E mode-switch guard is the Manager Batch observer's
// lease, not a stored PPU-local batch_id.

const appRoot = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, appRoot), "utf8");
}

test("Production Batch mode guard is held while the Manager Batch is non-terminal", async () => {
  const activity = await read("batch-execution-activity.ts");
  const production = await read("fleet/factory-console-v2.tsx");
  const nav = await read("global-nav.tsx");

  assert.match(activity, /export function beginBatchExecutionActivity/);
  assert.match(activity, /export function notifyBatchExecutionActivityChanged/);
  assert.match(activity, /return activeBatchExecutions;/);
  // The retired standalone reconnect handles no longer count as a lease.
  assert.doesNotMatch(activity, /hasUnresolvedStoredBatch|plasma-production-active-batch-v1|plasma-engineering-active-batch-v1/);
  assert.doesNotMatch(production, /plasma-production-active-batch-v1/);
  assert.match(nav, /getBatchExecutionActivityCount/);

  assert.match(production, /const MANAGED_BATCH_STORAGE_KEY = "plasma-managed-production-batch-v1";/);
  assert.match(production, /notifyBatchExecutionActivityChanged\(\)/);
  assert.match(production, /activityReleaseRef\.current = beginBatchExecutionActivity\(\);/);

  // The lease is released only on a terminal Manager Batch snapshot.
  const finalize = production.slice(
    production.indexOf("const finalizeBatch = useCallback"),
    production.indexOf("const applyBatchSnapshot = useCallback"),
  );
  assert.match(finalize, /if \(!terminalServerBatchStates\.has\(snapshot\.state\)\) return;[\s\S]*endActivity\(\);/);
  assert.match(production, /if \(terminalServerBatchStates\.has\(next\.state\)\) finalizeBatch\(next\)/);

  // A reload re-acquires the lease for a restored non-terminal Batch.
  assert.match(production, /beginActivity\(\);[\s\S]{0,200}\[BAT\] RESTORED · \$\{restored\.batch_id\}/);
  assert.match(production, /setBatchObservationState\("reconnecting"\)/);
});
