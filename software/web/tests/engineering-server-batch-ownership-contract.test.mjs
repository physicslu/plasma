import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, root), "utf8");
}

test("PMode and EMode Batch execution are both server-owned", async () => {
  const [pmod, emode, controller] = await Promise.all([
    read("fleet/factory-console-v2.tsx"),
    read("engineering/programming-workspace-v2.tsx"),
    read("engineering/engineering-server-batch.ts"),
  ]);

  assert.match(pmod, /createServerBatch\(/);
  assert.match(pmod, /getServerBatch\(/);
  assert.match(pmod, /cancelServerBatch\(/);

  assert.match(emode, /startEngineeringServerBatch\(/);
  assert.match(emode, /restoreEngineeringServerBatch\(/);
  assert.match(emode, /abortEngineeringServerBatch\(/);
  assert.match(controller, /createServerBatch\(/);
  assert.match(controller, /getServerBatch\(/);
  assert.match(controller, /cancelServerBatch\(/);
});

test("Engineering Batch orchestration cannot return to the browser", async () => {
  const emode = await read("engineering/programming-workspace-v2.tsx");
  assert.doesNotMatch(emode, /import \{ BatchLifecycle \}/);

  const runBatchStart = emode.indexOf("async function runBatch()");
  const cancelBatchStart = emode.indexOf("async function cancelBatch()", runBatchStart);
  assert.ok(runBatchStart >= 0 && cancelBatchStart > runBatchStart);
  const runBatch = emode.slice(runBatchStart, cancelBatchStart);

  assert.match(runBatch, /startEngineeringServerBatch\(apiBase/);
  assert.match(runBatch, /targets:\s*\[\{/);
  assert.match(runBatch, /facility_id:\s*selection\.facilityId/);
  assert.match(runBatch, /ppu_id:\s*selection\.ppuId/);
  assert.match(runBatch, /site_ids:\s*siteIds/);
  assert.match(runBatch, /executionPolicy:/);
  assert.doesNotMatch(runBatch, /new BatchLifecycle/);
  assert.doesNotMatch(runBatch, /for \(let round/);
  assert.doesNotMatch(runBatch, /for \(let attempt/);
  assert.doesNotMatch(runBatch, /startJob\(/);
  assert.doesNotMatch(runBatch, /requestCancel\(/);
});

test("Engineering Batch recovery and ABORT survive Programming surface unmount", async () => {
  const [emode, controller, activity] = await Promise.all([
    read("engineering/programming-workspace-v2.tsx"),
    read("engineering/engineering-server-batch.ts"),
    read("batch-execution-activity.ts"),
  ]);

  assert.match(controller, /plasma-engineering-active-batch-v1/);
  assert.match(controller, /sessionStorage\.setItem/);
  assert.match(controller, /sessionStorage\.getItem/);
  assert.match(controller, /beginBatchExecutionActivity\(/);
  assert.match(controller, /terminalServerBatchStates/);
  assert.match(controller, /observationState:\s*"reconnecting"/);
  assert.match(activity, /plasma-engineering-active-batch-v1/);

  const cancelBatchStart = emode.indexOf("async function cancelBatch()");
  const cancelSiteStart = emode.indexOf("async function cancelSite", cancelBatchStart);
  const cancelBatch = emode.slice(cancelBatchStart, cancelSiteStart);
  assert.match(cancelBatch, /abortEngineeringServerBatch\(apiBase\)/);
  assert.doesNotMatch(cancelBatch, /requestCancel\(/);
});

test("Engineering keeps direct single-Site Jobs separate from Batch ownership", async () => {
  const emode = await read("engineering/programming-workspace-v2.tsx");
  assert.match(emode, /async function runSite\(/);
  assert.match(emode, /startJob\(targetApiBase/);
  assert.match(emode, /if \(!targetApiBase \|\| batchRunning\) return/);
  assert.match(emode, /disabled=\{batchRunning \|\| !isRunning\(site\)\}/);
});

test("Mock settings remain immutable for an accepted server Batch", async () => {
  const controller = await read("engineering/engineering-server-batch.ts");
  const mockRuntime = await fs.readFile(new URL("../../../docs/architecture/mock-runtime-v1.1.md", import.meta.url), "utf8");

  assert.match(controller, /createServerBatch\(apiBase, options\)/);
  assert.match(mockRuntime, /One immutable Mock Profile snapshot/);
  assert.match(mockRuntime, /Editing Mock Settings while a Batch is running cannot alter that Batch/);
});
