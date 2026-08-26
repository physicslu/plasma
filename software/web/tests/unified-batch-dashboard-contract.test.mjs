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

test("Production and Engineering share neutral operator summary primitives", () => {
  assert.match(pmod, /OperatorKpiStrip/);
  assert.match(pmod, /OperatorPanel/);
  assert.match(operatorPanel, /export function OperatorKpiStrip/);
  assert.match(operatorPanel, /export function OperatorPanel/);
  assert.match(batchSummaryCss, /\.operatorKpiStrip/);
  assert.match(operatorCss, /\.operatorPanel/);
  assert.doesNotMatch(operatorCss, /\.operatorKpiStrip/);

  assert.match(emode, /OperatorKpiStrip/);
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

test("Engineering v2 policy is behavioral rather than decorative", () => {
  assert.match(emode, /for \(let round = 1; round <= repeatValue; round \+= 1\)/);
  assert.match(emode, /for \(let attempt = 0; attempt <= retryValue; attempt \+= 1\)/);
  assert.match(emode, /terminalize\(siteId, "faulted"/);
  assert.match(emode, /terminalize\(siteId, "error"/);
  assert.match(emode, /batchStopReason\.current = "threshold"/);
});
