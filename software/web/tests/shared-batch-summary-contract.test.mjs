import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const operatorPanel = fs.readFileSync(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
const batchSummaryCss = fs.readFileSync(new URL("../app/operator-ui/batch-summary.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("PMode and EMode share the canonical BatchSummary component", () => {
  assert.match(pmod, /OperatorKpiStrip/);
  assert.match(emode, /OperatorKpiStrip/);
  assert.match(operatorPanel, /export function BatchSummary/);
  assert.match(operatorPanel, /batchSummary operatorKpiSummary/);
  assert.match(operatorPanel, /export function OperatorKpiStrip\(props: BatchSummaryProps\)/);
  assert.match(operatorPanel, /return <BatchSummary \{\.\.\.props\} \/>/);
  assert.match(operatorPanel, /import "\.\/batch-summary\.css"/);
});

test("canonical BatchSummary style is based on the approved EMode KPI visual contract", () => {
  assert.match(batchSummaryCss, /min-height:\s*58px/);
  assert.match(batchSummaryCss, /padding:\s*8px 10px/);
  assert.match(batchSummaryCss, /font-size:\s*10px/);
  assert.match(batchSummaryCss, /article\[data-kpi="pass"\]/);
  assert.match(batchSummaryCss, /article\[data-kpi="fail"\]/);
  assert.match(batchSummaryCss, /border-left-width:\s*4px/);
  assert.match(batchSummaryCss, /border-left-color:\s*#15803d/);
  assert.match(batchSummaryCss, /border-left-color:\s*#dc2626/);
  assert.match(batchSummaryCss, /font-size:\s*30px/);
  assert.match(batchSummaryCss, /font-weight:\s*900/);
});
