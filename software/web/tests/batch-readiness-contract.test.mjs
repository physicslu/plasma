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

test("Emode shell density protects the Programming viewport with centered Batch status", async () => {
  const css = await read("engineering/engineering-density.css");
  const v2Css = await read("engineering/programming-workspace-v2.css");
  const refreshCss = await read("engineering/engineering-workspace-refresh.css");

  assert.match(css, /\.engineeringShell\s*\{[\s\S]*padding:\s*0;[\s\S]*gap:\s*0/);
  assert.match(css, /\.engineeringCanvas\.programmingActive\s*\{[\s\S]*padding:\s*10px 12px 18px/);
  assert.match(css, /\.programmingJobBody\.programmingBatchToolbar\s*\{[\s\S]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)[\s\S]*grid-template-areas:\s*none/);
  assert.match(css, /> \.engineeringPolicyRow\s*\{[\s\S]*grid-column:\s*4\s*\/\s*7;[\s\S]*grid-row:\s*2/);
  assert.match(css, /> \.engineeringReadRow\s*\{[\s\S]*display:\s*none/);
  assert.match(css, /> \.batchReadiness\s*\{[\s\S]*grid-column:\s*3\s*\/\s*5;[\s\S]*grid-row:\s*3/);
  assert.match(css, /> \.programmingActions\s*\{[\s\S]*grid-column:\s*1\s*\/\s*-1;[\s\S]*grid-row:\s*3;[\s\S]*width:\s*100%;[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*180px\s*minmax\(0,\s*1fr\)/);
  assert.match(css, /> \.programmingActions > button:first-child\s*\{[\s\S]*grid-column:\s*1;[\s\S]*width:\s*100%/);
  assert.match(css, /> \.programmingActions > button:last-child\s*\{[\s\S]*grid-column:\s*3;[\s\S]*width:\s*100%/);
  assert.match(css, /\[data-kpi="pass"\][\s\S]*border-left-color:\s*#15803d[\s\S]*background:\s*color-mix/);
  assert.match(css, /\[data-kpi="fail"\][\s\S]*border-left-color:\s*#dc2626[\s\S]*background:\s*color-mix/);
  assert.match(css, /\[data-kpi="pass"\] b,[\s\S]*\[data-kpi="fail"\] b[\s\S]*font-size:\s*30px/);
  assert.match(refreshCss, /\.engineeringWorkspace\s*\{[\s\S]*grid-template-columns:\s*224px minmax\(0, 1fr\)/);
  assert.match(refreshCss, /min-height:\s*calc\(100vh - 64px\)/);
  assert.match(refreshCss, /\.engineeringProgrammingV2 \.productionProgrammingWorkflow\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(v2Css, /\.engineeringProgrammingV2/);
  assert.match(v2Css, /\.productionProgrammingWorkflow/);
});