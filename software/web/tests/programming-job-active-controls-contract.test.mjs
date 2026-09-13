import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const panelPath = new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("active Programming Job exposes one execution status and one ABORT without the idle action row", async () => {
  const panel = await source(panelPath);

  assert.match(panel, /const executionActive = statusText \? activeExecutionStates\.has\(statusText\) : false/);
  assert.match(panel, /\{executionActive && \([\s\S]*className="programmingJobExecutionBar"[\s\S]*data-programming-job-action="status"/);
  assert.match(panel, /className="programmingJobExecutionAbort"[\s\S]*data-programming-job-action="abort"/);
  assert.match(panel, /\{!executionActive && \([\s\S]*className="programmingJobActionBar"/);

  for (const state of ["SUBMITTING", "QUEUED", "RUNNING", "RECONNECTING", "STOPPING", "ABORTING", "CANCELLING"]) {
    assert.match(panel, new RegExp(`"${state}"`));
  }

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
