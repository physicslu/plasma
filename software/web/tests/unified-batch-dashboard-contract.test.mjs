import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
const operatorPanel = fs.readFileSync(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
const operatorCss = fs.readFileSync(new URL("../app/operator-ui/operator-panel.css", import.meta.url), "utf8");
const batchSummaryCss = fs.readFileSync(new URL("../app/operator-ui/batch-summary.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/managed-programming-workspace.tsx", import.meta.url), "utf8");
const statistics = fs.readFileSync(new URL("../app/programming/batch-statistics.ts", import.meta.url), "utf8");

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
  // Batch Statistics v1: one KPI definition shared with EMode.
  for (const label of ["SITES", "TOTAL IC", "PROCESSED IC", "PASS IC", "FAIL IC", "YIELD", "BATCH TIME",
    "PHYSICAL IC", "TOTAL CYCLES", "SETTLED CYCLES", "PASS CYCLES", "FAIL CYCLES", "CYCLE PASS RATE"]) {
    assert.match(statistics, new RegExp(`label: \\\"${label}\\\"`));
  }
  assert.match(pmod, /snapshotStatistics\(\{\s*sites: batchSnapshot\.sites,\s*repeat: batchSnapshot\.execution_policy\.repeat_count,/);
  assert.match(pmod, /batchStatistics\(\{ sites: batchCounts\.sites, repeat: repeatValue \?\? 0,/);
  assert.match(pmod, /formatBatchTime\(batchSnapshot, clockNow\)/);
  assert.match(pmod, /displayedBatchSelection = serverBatchRunning \? serverBatchMembership : batchSelection/);
  // One column per KPI (7 Replace IC, 8 Same-IC Debug); 7 when unset.
  assert.match(batchSummaryCss, /grid-template-columns:\s*repeat\(var\(--batch-summary-columns, 7\), minmax\(0, 1fr\)\)/);
});

test("Production manufacturing KPIs use Manager Batch truth and exclude cancelled work from Yield", () => {
  // U10: the snapshot is the Manager Batch journal, never a PPU-local Batch store.
  assert.match(pmod, /applyBatchSnapshot\(managedProductionSnapshot\(next, managedTopology\), catalog\)/);
  assert.doesNotMatch(pmod, /server-batch-api|server-batch-snapshot-store|publishServerBatchSnapshot/);
  assert.match(statistics, /site\.pass_rounds \?\? site\.completed_rounds/);
  assert.match(statistics, /site\.final_failures/);
  const snapshot = statistics.slice(statistics.indexOf("export function snapshotStatistics"), statistics.indexOf("export function passRate"));
  assert.doesNotMatch(snapshot, /cancelled/);
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
  assert.match(pmod, /await stopProgrammingBatch\(activeBatchId\)/);
  assert.doesNotMatch(pmod, /cancelServerBatch/);
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

test("Engineering submits Batch policy once and the Manager owns repeat, retry, and stop behavior", () => {
  assert.match(emode, /const policy = \{ retryLimit, stopPolicy, repeat: repeatValue, replaceIc \};/);
  assert.equal((emode.match(/runManagedBatch\(request, \{/g) ?? []).length, 1);
  assert.doesNotMatch(emode, /for \(let round|for \(let attempt|startJob\(|startEngineeringServerBatch/);
});
