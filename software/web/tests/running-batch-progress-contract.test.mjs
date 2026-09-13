import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const summaryPath = new URL("../app/operator-ui/batch-summary.tsx", import.meta.url);
const livePath = new URL("../app/operator-ui/batch-summary-live.ts", import.meta.url);
const jobPath = new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("persistent execution bar mirrors shared Batch Summary progress without owning execution state", async () => {
  const [summary, live, job] = await Promise.all([
    source(summaryPath),
    source(livePath),
    source(jobPath),
  ]);

  assert.match(summary, /batchSummaryChannelFromAriaLabel\(ariaLabel\)/);
  assert.match(summary, /\["sites", "production-sites"\]/);
  assert.match(summary, /\["processed-ic"\]/);
  assert.match(summary, /\["total-ic"\]/);
  assert.match(summary, /publishBatchSummaryLiveMetrics/);

  assert.match(live, /Production Batch Summary/);
  assert.match(live, /Engineering Batch Summary/);
  assert.match(job, /useBatchSummaryLiveMetrics\(mode\)/);
  assert.match(job, /SITES \$\{liveMetrics\.sites\} · PROCESSED \$\{liveMetrics\.processedIc\}\/\$\{liveMetrics\.totalIc\}/);
  assert.match(job, /activeExecutionStates\.has\(statusText\)/);

  for (const forbidden of [
    "createServerBatch",
    "cancelServerBatch",
    "getServerBatch",
    "evaluateBatchReadiness",
    "fetch(",
    "sessionStorage",
    "localStorage",
  ]) {
    assert.equal(live.includes(forbidden), false, `live summary bridge must not own execution token: ${forbidden}`);
  }
});
