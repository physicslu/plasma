import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
const operatorPanel = fs.readFileSync(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
const operatorCss = fs.readFileSync(new URL("../app/operator-ui/operator-panel.css", import.meta.url), "utf8");
const batchSummaryCss = fs.readFileSync(new URL("../app/operator-ui/batch-summary.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const serverBatchApi = fs.readFileSync(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");
const snapshotStore = fs.readFileSync(new URL("../app/server-batch-snapshot-store.ts", import.meta.url), "utf8");
const serverBatchRuntime = fs.readFileSync(new URL("../../python/plasma_web/batch_runtime.py", import.meta.url), "utf8");

test("Production and Engineering share neutral operator summary primitives", () => {
  assert.match(pmod, /BatchSummary/);
  assert.match(pmod, /OperatorPanel/);
  assert.doesNotMatch(pmod, /OperatorKpiStrip/);
  assert.match(operatorPanel, /export function OperatorPanel/);
  assert.doesNotMatch(operatorPanel, /BatchSummary|OperatorKpiStrip|operatorKpiStrip/);
  assert.match(batchSummaryCss, /\.batchSummaryGrid/);
  assert.doesNotMatch(batchSummaryCss, /\.operatorKpiStrip/);
  assert.match(operatorCss, /\.operatorPanel/);
  assert.doesNotMatch(operatorCss, /\.operatorKpiStrip|\.batchSummaryGrid/);

  assert.match(emode, /BatchSummary/);
  assert.doesNotMatch(emode, /OperatorKpiStrip/);
  assert.match(emode, /ariaLabel="Engineering Batch Summary"/);
  assert.match(emode, /PROGRAMMING JOB/);
  assert.match(emode, /LIVE SITE STATUS/);
  assert.doesNotMatch(emode, /BatchTopologySummary/);
  assert.doesNotMatch(emode, /ActiveFpsSummary/);
});

test("Production KPI row separates equipment scope, planned IC quantity, and processed IC outcomes", () => {
  for (const label of ["SITES", "TOTAL IC", "PROCESSED IC", "PASS", "FAIL", "YIELD", "BATCH TIME"]) {
    assert.match(pmod, new RegExp(`label: \\\"${label}\\\"`));
  }
  assert.match(pmod, /value:\s*batchSnapshot\?\.sites\.length \?\? batchCounts\.sites/);
  assert.match(pmod, /batchSnapshot\.sites\.length \* batchSnapshot\.execution_policy\.repeat_count/);
  assert.match(pmod, /value:\s*plannedIcCount/);
  assert.match(pmod, /formatBatchTime\(batchSnapshot, clockNow\)/);
  assert.match(pmod, /label: \"PROCESSED IC\", value: manufacturing\.total/);
  assert.match(pmod, /displayedBatchSelection = serverBatchRunning \? serverBatchMembership : batchSelection/);
  assert.match(batchSummaryCss, /grid-template-columns:\s*repeat\(7, minmax\(0, 1fr\)\)/);
});

test("Production manufacturing KPIs use server Batch truth and exclude cancelled work from Yield", () => {
  assert.match(snapshotStore, /latestSnapshot/);
  assert.match(serverBatchApi, /publishServerBatchSnapshot/);
  assert.equal((serverBatchApi.match(/return observeBatchSnapshot\(payload\.batch\);/g) ?? []).length, 4);
  assert.match(pmod, /site\.completed_rounds/);
  assert.match(pmod, /site\.final_failures/);
  assert.match(pmod, /const total = pass \+ fail/);
  const manufacturing = pmod.slice(pmod.indexOf("const manufacturing = useMemo"), pmod.indexOf("const repeatValue"));
  assert.doesNotMatch(manufacturing, /cancelled/);
});

test("Production Site Selection stays tree-based and can be hidden without deleting the Production Set", () => {
  assert.match(pmod, /<details className="productionTreeFacility"/);
  assert.match(pmod, /<details className="productionTreePpu"/);
  assert.match(pmod, /pmodSelectorCollapsed/);
  assert.match(pmod, /aria-expanded=\{!selectorCollapsed\}/);
  assert.match(pmodCss, /\.productionSiteSelection\.is-collapsed \.operatorPanelBody\s*\{\s*display:\s*none;/s);
});

test("Production next-Batch membership is independently selectable at PPU and Site level before START", () => {
  assert.match(pmod, /pmodBatchSelection/);
  assert.match(pmod, /toggleBatchPpu/);
  assert.match(pmod, /toggleBatchSite/);
  assert.match(pmod, /Batch select \$\{active\.target\.display_name\}/);
  assert.match(pmod, /data-batch-selected/);
  assert.match(pmod, /disabled=\{batchRunning \|\| !site\.enabled\}/);
});

test("Production running Batch exposes only whole-Batch ABORT", () => {
  assert.match(pmod, /async function abortBatch/);
  assert.match(pmod, /cancelServerBatch\(/);
  assert.doesNotMatch(pmod, /cancelServerBatchPPU/);
  assert.doesNotMatch(pmod, /Cancel PPU/);
  assert.match(pmod, /Membership is immutable after START/i);
  assert.match(pmod, /only whole-Batch ABORT/);
});

test("Production LED board remains the primary high-density runtime surface", () => {
  assert.match(pmod, /factorySiteLedGrid/);
  assert.match(pmod, /factorySiteLedCard/);
  assert.match(pmod, /densityFor\(productionSetCounts\.sites\)/);
  assert.match(pmodCss, /--site-card-w/);
  assert.match(pmodCss, /\.factoryPpuRows\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(pmodCss, /factoryRunningPulse 1s/);
  assert.match(pmodCss, /factorySiteLed\[data-state="ready"\]/);
  assert.match(pmodCss, /factorySiteLed\[data-state="running"\]/);
  assert.match(pmodCss, /factorySiteLed\[data-state="success"\]/);
  assert.match(pmodCss, /factorySiteLed\[data-state="faulted"\]/);
});

test("Engineering v2 submits Batch policy once and the server runtime owns repeat, retry, and stop behavior", () => {
  const runBatchStart = emode.indexOf("async function runBatch()");
  const cancelBatchStart = emode.indexOf("async function cancelBatch()", runBatchStart);
  assert.ok(runBatchStart >= 0 && cancelBatchStart > runBatchStart);
  const runBatch = emode.slice(runBatchStart, cancelBatchStart);

  assert.match(runBatch, /startEngineeringServerBatch\(apiBase/);
  assert.match(runBatch, /repeat_count:\s*repeatValue/);
  assert.match(runBatch, /site_retry_limit:\s*retryValue/);
  assert.match(runBatch, /failed_site_stop_threshold:\s*thresholdValue/);
  assert.doesNotMatch(runBatch, /for \(let round/);
  assert.doesNotMatch(runBatch, /for \(let attempt/);
  assert.doesNotMatch(runBatch, /startJob\(/);

  assert.match(serverBatchRuntime, /for round_index in range\(1, batch\.policy\.repeat_count \+ 1\):/);
  assert.match(serverBatchRuntime, /max_retries=batch\.policy\.site_retry_limit/);
  assert.match(serverBatchRuntime, /threshold = batch\.policy\.failed_site_stop_threshold/);
  assert.match(serverBatchRuntime, /batch\.stop_reason = "failed_site_threshold"/);
});