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
  assert.match(batchSummary, /className=\{`batchSummary \$\{title \? "has-title" : ""\}`\.trim\(\)\}/);
  assert.match(batchSummary, /className="batchSummaryHeader"/);
  assert.match(batchSummary, /className="batchSummaryGrid"/);
  assert.match(batchSummary, /import "\.\/batch-summary\.css"/);
  assert.doesNotMatch(batchSummary, /import "\.\/operator-panel\.css"/);
  assert.doesNotMatch(batchSummary, /operatorKpiSummary|operatorKpiStrip/);

  // The old public name is temporarily an API-only export alias. There must be
  // no wrapper function, local BatchSummary import, markup, or style ownership.
  assert.match(operatorPanel, /BatchSummary as OperatorKpiStrip/);
  assert.doesNotMatch(operatorPanel, /export function OperatorKpiStrip/);
  assert.doesNotMatch(operatorPanel, /return <BatchSummary/);
  assert.doesNotMatch(operatorPanel, /import \{ BatchSummary/);
});

test("BatchSummary owns its complete internal visual contract", () => {
  assert.match(batchSummaryCss, /\.batchSummary\.has-title/);
  assert.match(batchSummaryCss, /\.batchSummaryHeader/);
  assert.match(batchSummaryCss, /\.batchSummaryGrid/);
  assert.doesNotMatch(batchSummaryCss, /operatorKpiSummary|operatorKpiStrip/);
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
  const internalSelectors = /operatorKpiSummary|operatorKpiStrip|batchSummaryHeader|batchSummaryGrid|data-kpi=/;
  assert.doesNotMatch(operatorPanelCss, internalSelectors);
  assert.doesNotMatch(densityCss, internalSelectors);
  assert.doesNotMatch(readabilityCss, internalSelectors);
  assert.doesNotMatch(emodeCss, /batchSummaryHeader|batchSummaryGrid article|data-kpi=/);
  assert.match(emodeCss, /\.engineeringProgrammingV2 \.batchSummary\s*\{\s*margin-top:\s*7px;/);
});
