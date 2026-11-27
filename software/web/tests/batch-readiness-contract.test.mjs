import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, root), "utf8");
}

test("PMode and Engineering Programming share one batch readiness source of truth", async () => {
  const readiness = await read("batch-readiness.ts");
  const pmodRoute = await read("fleet/page.tsx");
  const pmod = await read("fleet/factory-console-v2.tsx");
  const emode = await read("engineering/managed-programming-workspace.tsx");
  const sharedJob = await read("operator-ui/programming-job-panel.tsx");

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

  assert.match(readiness, /export type BatchReadinessCode/);
  assert.match(readiness, /export function batchReadinessGuidanceFromLabel/);
  assert.match(pmodRoute, /factory-console-v2/);
  // U10: PMode readiness is the Manager admission, typed by the shared codes.
  assert.match(pmod, /import type \{ BatchReadinessCode \} from "\.\.\/batch-readiness";/);
  assert.match(pmod, /const batchReadiness = managedReadiness;/);
  assert.match(sharedJob, /batchReadinessGuidanceFromLabel/);
  // Manual Repeat: the same START is the Continue of waiting Sites; otherwise readiness gates it.
  assert.match(pmod, /startDisabled=\{waitingSites\.length \? !continuingSites\.length : !batchReadiness\.ready \|\| !policyValid\}/);
  // EMode readiness comes from the Manager Route/Fleet admission (U10: managed only).
  assert.match(emode, /startDisabled=\{waiting\.length \? !continuing\.length : !readiness\.ready \|\| repeatValue == null\}/);
  assert.match(sharedJob, /disabled=\{startDisabled\}/);
});

test("Production and Engineering feed mode behavior into one ProgrammingJobPanel", async () => {
  const pmod = await read("fleet/factory-console-v2.tsx");
  const emode = await read("engineering/managed-programming-workspace.tsx");
  const sharedPanel = await read("operator-ui/operator-panel.tsx");
  const sharedJob = await read("operator-ui/programming-job-panel.tsx");

  assert.match(pmod, /BatchSummary/);
  assert.match(emode, /BatchSummary/);
  assert.doesNotMatch(pmod, /OperatorKpiStrip/);
  assert.doesNotMatch(emode, /OperatorKpiStrip/);
  assert.match(pmod, /<ProgrammingJobPanel[\s\S]*mode="production"/);
  assert.match(emode, /<ProgrammingJobPanel[\s\S]*mode="engineering"/);
  assert.match(sharedJob, /ICPickerField/);
  assert.match(sharedJob, /ProgrammingJobImage/);
  assert.match(sharedJob, /ProgrammingJobPolicy/);
  assert.match(sharedJob, /data-programming-job-action="start"/);
  assert.match(sharedJob, /data-programming-job-action="status"/);
  assert.match(sharedJob, /data-programming-job-action="abort"/);
  assert.doesNotMatch(sharedPanel, /BatchSummary|OperatorKpiStrip|operatorKpiStrip/);
  assert.match(sharedPanel, /operatorPanel/);

  assert.match(emode, /Site Retry Limit/);
  assert.doesNotMatch(emode, /BatchTopologySummary/);
});

test("Engineering density owns the workspace, not Programming Job internals", async () => {
  const css = await read("engineering/engineering-density.css");
  const v2Css = await read("engineering/programming-workspace-v2.css");
  const refreshCss = await read("engineering/engineering-workspace-refresh.css");
  const batchSummaryCss = await read("operator-ui/batch-summary.css");
  const controlsCss = await read("operator-ui/programming-job-controls.css");
  const designCss = await read("operator-ui/operator-design-contract.css");

  assert.match(css, /\.engineeringShell\s*\{[\s\S]*padding:\s*0;[\s\S]*gap:\s*0/);
  assert.match(css, /\.engineeringCanvas\.programmingActive\s*\{[\s\S]*padding:\s*10px 12px 18px/);
  assert.doesNotMatch(css, /\.programmingJobGrid\b|\.programmingJobField\b|\.programmingJobActionBar\b|\.programmingJobStatus\b/);
  assert.doesNotMatch(v2Css, /\.programmingJobGrid\b|\.programmingJobField\b|\.programmingJobActionBar\b|\.programmingJobStatus\b/);
  assert.doesNotMatch(refreshCss, /\.programmingJobGrid\b|\.programmingJobField\b|\.programmingJobActionBar\b|\.programmingJobStatus\b/);

  assert.match(controlsCss, /\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1\.08fr\) minmax\(0, 1fr\)/);
  assert.match(controlsCss, /\.programmingJobStatus\s*\{[\s\S]*min-height:\s*var\(--operator-action-min-height\)/);
  assert.match(designCss, /--operator-action-min-height:\s*40px/);
  assert.doesNotMatch(controlsCss, /\.programmingJobStatus\s*\{[\s\S]*min-height:\s*64px/);
  assert.doesNotMatch(controlsCss, /position:\s*absolute/);

  assert.doesNotMatch(css, /operatorKpiStrip|batchSummary(?:Header|Grid)|data-kpi=/);
  assert.match(batchSummaryCss, /\[data-kpi="pass"\][\s\S]*border-left-color:\s*#15803d[\s\S]*background:\s*color-mix/);
  assert.match(batchSummaryCss, /\[data-kpi="fail"\][\s\S]*border-left-color:\s*#dc2626[\s\S]*background:\s*color-mix/);
  assert.match(batchSummaryCss, /\[data-kpi="pass"\] b,[\s\S]*\[data-kpi="fail"\] b[\s\S]*font-size:\s*30px/);
  assert.match(refreshCss, /\.engineeringWorkspace\s*\{[\s\S]*grid-template-columns:\s*224px minmax\(0, 1fr\)/);
  assert.match(refreshCss, /min-height:\s*calc\(100vh - 64px\)/);
  assert.match(refreshCss, /\.engineeringProgrammingV2 \.productionProgrammingWorkflow\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(v2Css, /\.engineeringProgrammingV2/);
});
