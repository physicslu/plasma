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
  const pmod = await read("fleet/factory-console-v2.tsx");
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
  assert.match(pmodRoute, /factory-console-v2/);
  assert.match(pmod, /evaluateBatchReadiness\(/);
  assert.match(emode, /evaluateBatchReadiness\(/);
  assert.match(pmod, /disabled=\{!batchReadiness\.ready \|\| !policyValid\}/);
  assert.match(emode, /disabled=\{!batchReadiness\.ready \|\| !policyValid\}/);
});

test("Production and Engineering share operator programming vocabulary while keeping mode-specific ownership", async () => {
  const pmod = await read("fleet/factory-console-v2.tsx");
  const emode = await read("engineering/programming-workspace-v2.tsx");
  const sharedPanel = await read("operator-ui/operator-panel.tsx");

  assert.match(pmod, /BatchSummary/);
  assert.match(emode, /BatchSummary/);
  assert.doesNotMatch(pmod, /OperatorKpiStrip/);
  assert.doesNotMatch(emode, /OperatorKpiStrip/);
  assert.match(pmod, /OperatorPanel/);
  assert.match(pmod, /PROGRAMMING JOB/);
  assert.match(pmod, /START PROGRAMMING/);
  assert.match(pmod, /LIVE SITE STATUS/);
  assert.match(pmod, /ICPickerField/);
  assert.match(pmod, /Programming Image/);
  assert.doesNotMatch(sharedPanel, /BatchSummary|OperatorKpiStrip|operatorKpiStrip/);
  assert.match(sharedPanel, /operatorPanel/);

  assert.match(emode, /PROGRAMMING JOB/);
  assert.match(emode, /START PROGRAMMING/);
  assert.match(emode, /Site Retry Limit/);
  assert.doesNotMatch(emode, /BatchTopologySummary/);
});

test("Emode density owns placement while shared Programming Job controls own centered Batch status", async () => {
  const css = await read("engineering/engineering-density.css");
  const v2Css = await read("engineering/programming-workspace-v2.css");
  const refreshCss = await read("engineering/engineering-workspace-refresh.css");
  const batchSummaryCss = await read("operator-ui/batch-summary.css");
  const controlsCss = await read("operator-ui/programming-job-controls.css");

  assert.match(css, /\.engineeringShell\s*\{[\s\S]*padding:\s*0;[\s\S]*gap:\s*0/);
  assert.match(css, /\.engineeringCanvas\.programmingActive\s*\{[\s\S]*padding:\s*10px 12px 18px/);
  assert.match(css, /\.programmingJobBody\.programmingBatchToolbar\s*\{[\s\S]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)[\s\S]*grid-template-areas:\s*none/);
  assert.match(css, /> \.engineeringPolicyRow\s*\{[\s\S]*grid-column:\s*4\s*\/\s*7;[\s\S]*grid-row:\s*2/);
  assert.match(css, /> \.engineeringReadRow\s*\{[\s\S]*display:\s*none/);
  assert.match(css, /> \.programmingActions\s*\{[\s\S]*grid-column:\s*1\s*\/\s*-1;[\s\S]*grid-row:\s*3;[\s\S]*width:\s*100%/);
  assert.doesNotMatch(css, /> \.batchReadiness\s*\{/);
  assert.doesNotMatch(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s*180px\s*minmax\(0,\s*1fr\)/);
  assert.doesNotMatch(css, /> \.programmingActions > button/);

  assert.match(controlsCss, /\.factoryActionBar,[\s\S]*\.engineeringProgrammingV2 \.programmingJobCard \.programmingActions/);
  assert.match(controlsCss, /grid-template-columns:\s*minmax\(0, 1fr\) 160px minmax\(0, 1fr\)/);
  assert.match(controlsCss, /\.factoryBatchStatus,[\s\S]*\.engineeringProgrammingV2 \.programmingJobCard \.batchReadiness/);

  assert.doesNotMatch(css, /operatorKpiStrip|batchSummary(?:Header|Grid)|data-kpi=/);
  assert.match(batchSummaryCss, /\[data-kpi="pass"\][\s\S]*border-left-color:\s*#15803d[\s\S]*background:\s*color-mix/);
  assert.match(batchSummaryCss, /\[data-kpi="fail"\][\s\S]*border-left-color:\s*#dc2626[\s\S]*background:\s*color-mix/);
  assert.match(batchSummaryCss, /\[data-kpi="pass"\] b,[\s\S]*\[data-kpi="fail"\] b[\s\S]*font-size:\s*30px/);
  assert.match(refreshCss, /\.engineeringWorkspace\s*\{[\s\S]*grid-template-columns:\s*224px minmax\(0, 1fr\)/);
  assert.match(refreshCss, /min-height:\s*calc\(100vh - 64px\)/);
  assert.match(refreshCss, /\.engineeringProgrammingV2 \.productionProgrammingWorkflow\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(v2Css, /\.engineeringProgrammingV2/);
  assert.match(v2Css, /\.productionProgrammingWorkflow/);
});
