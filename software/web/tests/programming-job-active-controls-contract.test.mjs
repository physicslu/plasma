import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const panelPath = new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Programming Job keeps the canonical START / Batch Status / ABORT row during execution", async () => {
  const panel = await source(panelPath);

  assert.match(panel, /className="programmingJobActionBar"[\s\S]*data-programming-job-actions=\{mode\}/);
  assert.match(panel, /data-programming-job-action="start"/);
  assert.match(panel, /data-programming-job-action="status"/);
  assert.match(panel, /data-programming-job-action="abort"/);

  assert.doesNotMatch(panel, /programmingJobExecutionBar/);
  assert.doesNotMatch(panel, /programmingJobExecutionAbort/);
  assert.doesNotMatch(panel, /activeExecutionStates/);
  assert.doesNotMatch(panel, /useBatchSummaryLiveMetrics/);

  for (const forbidden of [
    "createServerBatch",
    "cancelServerBatch",
    "getServerBatch",
    "fetch(",
    "sessionStorage",
    "localStorage",
  ]) {
    assert.equal(panel.includes(forbidden), false, `shared Programming Job must not own Batch execution: ${forbidden}`);
  }
});
