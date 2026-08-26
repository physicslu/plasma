import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const operatorPanel = fs.readFileSync(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
const operatorPanelCss = fs.readFileSync(new URL("../app/operator-ui/operator-panel.css", import.meta.url), "utf8");
const batchSummary = fs.readFileSync(new URL("../app/operator-ui/batch-summary.tsx", import.meta.url), "utf8");
const batchSummaryCss = fs.readFileSync(new URL("../app/operator-ui/batch-summary.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const emodeCss = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");
const densityCss = fs.readFileSync(new URL("../app/engineering/engineering-density.css", import.meta.url), "utf8");
const readabilityCss = fs.readFileSync(new URL("../app/engineering/engineering-readability.css", import.meta.url), "utf8");

test("PMode and EMode share the canonical BatchSummary component", () => {
  assert.match(pmod, /OperatorKpiStrip/);
  assert.match(emode, /OperatorKpiStrip/);
  assert.match(batchSummary, /export function BatchSummary/);
  assert.match(batchSummary, /batchSummary operatorKpiSummary/);
  assert.match(batchSummary, /import "\.\/batch-summary\.css"/);
  assert.match(operatorPanel, /import \{ BatchSummary, type BatchSummaryProps \} from "\.\/batch-summary"/);
  assert.match(operatorPanel, /export function OperatorKpiStrip\(props: BatchSummaryProps\)/);
  assert.match(operatorPanel, /return <BatchSummary \{\.\.\.props\} \/>/);
  assert.match(operatorPanel, /export \{ BatchSummary, type BatchSummaryProps, type OperatorKpi \} from "\.\/batch-summary"/);
});

test("BatchSummary owns its complete internal visual contract", () => {
  assert.match(batchSummaryCss, /font-family:\s*var\(--font-sans\),\s*Arial,\s*sans-serif/);
  assert.match(batchSummaryCss, /font-variant-numeric:\s*tabular-nums/);
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
  assert.match(batchSummaryCss, /@container \(max-width:\s*1050px\)/);
  assert.match(batchSummaryCss, /@container \(max-width:\s*700px\)/);
});

test("mode-local CSS cannot override BatchSummary internal typography or PASS FAIL semantics", () => {
  assert.doesNotMatch(operatorPanelCss, /operatorKpiSummary|operatorKpiStrip/);
  assert.doesNotMatch(densityCss, /operatorKpiStrip|data-kpi=/);
  assert.doesNotMatch(readabilityCss, /operatorKpiStrip|data-kpi=/);
  assert.doesNotMatch(emodeCss, /operatorKpiStrip article|data-kpi=/);
  assert.match(emodeCss, /\.engineeringProgrammingV2 \.batchSummary\s*\{\s*margin-top:\s*7px;/);
});
