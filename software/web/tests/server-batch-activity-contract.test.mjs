import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const appRoot = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, appRoot), "utf8");
}

test("Production Batch mode guard stays fail-closed while an unresolved batch_id is stored", async () => {
  const activity = await read("batch-execution-activity.ts");
  const production = await read("fleet/factory-console-v2.tsx");

  const storageKey = "plasma-production-active-batch-v1";
  assert.match(activity, new RegExp(storageKey));
  assert.match(production, new RegExp(storageKey));
  assert.match(activity, /hasUnresolvedStoredBatch/);
  assert.match(activity, /Math\.max\(activeBatchExecutions, hasUnresolvedStoredBatch\(\) \? 1 : 0\)/);
  assert.match(activity, /export function notifyBatchExecutionActivityChanged/);
  assert.match(production, /notifyBatchExecutionActivityChanged\(\)/);

  const terminal = production.indexOf("const finalizeBatch = useCallback");
  const clear = production.indexOf("clearStoredBatch();", terminal);
  const release = production.indexOf("endActivity();", clear);
  assert.notEqual(terminal, -1, "terminal Batch handling is missing");
  assert.notEqual(clear, -1, "terminal Batch must clear the reconnect hint");
  assert.notEqual(release, -1, "terminal Batch must release execution activity");
  assert.ok(terminal < clear && clear < release, "terminal path must clear stored Batch before releasing the mode guard");
  assert.match(production, /if \(terminalServerBatchStates\.has\(next\.state\)\) finalizeBatch\(next\)/);
  assert.match(production, /setBatchObservationState\("reconnecting"\)/);
  assert.match(production, /OBSERVATION RESTORED/);
});
