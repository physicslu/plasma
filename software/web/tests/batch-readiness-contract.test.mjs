import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, root), "utf8");
}

test("Pmod and Engineering Programming v2 share one batch readiness source of truth", async () => {
  const readiness = await read("batch-readiness.ts");
  const pmodRoute = await read("fleet/page.tsx");
  const pmod = await read("fleet/server-batch-page.tsx");
  const emode = await read("engineering/programming-workspace-v2.tsx");

  for (const label of [
    "BATCH READY",
    "NO TARGET",
    "NO SITE",
    "NO OP",
    "IMAGE REQUIRED",
    "IMAGE INVALID",
    "INVALID READ",
    "PPU OFFLINE",
    "SITE BUSY",
    "RUNNING",
    "CANCELLING",
  ]) assert.match(readiness, new RegExp(label.replace(/ /g, "\\s")));

  assert.match(readiness, /export function evaluateBatchReadiness/);
  assert.match(pmodRoute, /server-batch-page/);
  assert.match(pmod, /evaluateBatchReadiness\(/);
  assert.match(emode, /evaluateBatchReadiness\(/);
  assert.match(pmod, /disabled=\{!batchReadiness\.ready \|\| !policyValid\}/);
  assert.match(emode, /disabled=\{!batchReadiness\.ready \|\| !policyValid\}/);
});

test("Production and Engineering v2 share programming control vocabulary without sharing layout ownership", async () => {
  const pmod = await read("fleet/server-batch-page.tsx");
  const emode = await read("engineering/programming-workspace-v2.tsx");

  assert.match(pmod, /programmingBatchToolbar/);
  assert.match(emode, /programmingBatchToolbar/);
  assert.match(pmod, /programmingFileName/);
  assert.match(emode, /programmingFileName/);
  assert.match(pmod, /programmingBatchOperations/);
  assert.match(emode, /programmingBatchOperations/);
  assert.match(emode, /PROGRAMMING JOB/);
  assert.match(emode, /START PROGRAMMING/);
  assert.match(emode, /Site Retry Limit/);
  assert.doesNotMatch(emode, /BatchTopologySummary/);
});

test("Emode shell density still protects the Programming v2 viewport", async () => {
  const css = await read("engineering/engineering-density.css");
  const v2Css = await read("engineering/programming-workspace-v2.css");
  assert.match(css, /\.engineeringShell\s*\{[\s\S]*padding:\s*18px clamp\(12px, 1\.8vw, 28px\) 36px/);
  assert.match(css, /\.engineeringHeading\s*\{[\s\S]*min-height:\s*54px/);
  assert.match(v2Css, /\.engineeringProgrammingV2/);
  assert.match(v2Css, /\.productionProgrammingWorkflow/);
});