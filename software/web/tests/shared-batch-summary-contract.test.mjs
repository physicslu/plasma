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

test("PMode and EMode import the canonical BatchSummary directly", () => {
  assert.match(pmod, /import \{ BatchSummary \} from "\.\.\/operator-ui\/batch-summary"/);
  assert.match(emode, /import \{ BatchSummary \} from "\.\.\/operator-ui\/batch-summary"/);
  assert.match(pmod, /<BatchSummary/);
  assert.match(emode, /<BatchSummary/);
  assert.doesNotMatch(pmod, /OperatorKpiStrip/);
  assert.doesNotMatch(emode, /OperatorKpiStrip/);

  assert.match(batchSummary, /export function BatchSummary/);
  assert.match(batchSummary, /import \{ OperatorPanelHeader \} from "\.\/operator-panel"/);
  assert.match(batchSummary, /<OperatorPanelHeader title=\{title\} meta=\{meta\} \/>/);
  assert.match(batchSummary, /className="batchSummaryGrid"/);
  assert.match(batchSummary, /import "\.\/batch-summary\.css"/);
  assert.doesNotMatch(batchSummary, /batchSummaryHeader|operatorKpiSummary|operatorKpiStrip/);

  assert.match(operatorPanel, /export function OperatorPanelHeader/);
  assert.doesNotMatch(operatorPanel, /BatchSummary|OperatorKpiStrip|operatorKpiStrip/);
});

test("BatchSummary owns KPI body presentation while OperatorPanelHeader owns title presentation", () => {
  assert.match(batchSummaryCss, /\.batchSummary\.has-title/);
  assert.match(batchSummaryCss, /\.batchSummaryGrid/);
  assert.doesNotMatch(batchSummaryCss, /\.batchSummaryHeader/);
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

test("mode-local CSS cannot override BatchSummary KPI internals or shared title ownership", () => {
  const internalSelectors = /operatorKpiSummary|operatorKpiStrip|batchSummaryHeader|batchSummaryGrid|data-kpi=/;
  assert.doesNotMatch(operatorPanelCss, /batchSummaryHeader|batchSummaryGrid|data-kpi=/);
  assert.doesNotMatch(densityCss, internalSelectors);
  assert.doesNotMatch(readabilityCss, internalSelectors);
  assert.doesNotMatch(emodeCss, /batchSummaryHeader|batchSummaryGrid article|data-kpi=/);
  assert.match(emodeCss, /\.engineeringProgrammingV2 \.batchSummary\s*\{\s*margin-top:\s*7px;/);
});


test("Manager Batch Time uses authoritative wall clock, freezes and rejects missing or invalid evidence", () => {
  // Execute the actual formatting function; no second implementation of the clock.
  const source = pmod.slice(pmod.indexOf("function formatBatchTime("), pmod.indexOf("function ppuState("));
  const js = source.replace("snapshot: ServerBatchSnapshot | null, now: number): string", "snapshot, now)");
  const format = new Function("terminalServerBatchStates", `${js}; return formatBatchTime;`)(
    new Set(["success", "partial", "error", "cancelled"]));
  const start = "2026-11-16T12:00:00+00:00";
  const end = "2026-11-16T12:00:16+00:00";
  const now = Date.parse(start) + 9000;
  assert.equal(format(null, now), "00:00:00");
  assert.equal(format({ state: "queued" }, now), "00:00:00");
  assert.equal(format({ state: "running", started_at: start }, now), "00:00:09");
  for (const state of ["success", "partial", "error", "cancelled"]) {
    for (const count of [1, 2, 8]) {
      const snapshot = { state, started_at: start, finished_at: end,
        sites: Array.from({ length: count }, () => ({ duration_ms: 16000 })) };
      assert.equal(format(snapshot, now + 600000), "00:00:16");
      assert.equal(format(snapshot, now + 900000), "00:00:16");
    }
    assert.equal(format({ state, started_at: start }, now), "UNKNOWN");
    assert.equal(format({ state, updated_at: end, created_at: start }, now), "UNKNOWN");
  }
  for (const [started_at, finished_at] of [["invalid", end], [start, "invalid"], [end, start]]) {
    assert.equal(format({ state: "success", started_at, finished_at }, now), "UNKNOWN");
  }
});


test("terminal Start reconciliation retains the Batch before releasing its hold", () => {
  const reconcile = pmod.slice(pmod.indexOf("const batch = await getProgrammingBatch(reconciled.batch.batch_id)"));
  assert.match(reconcile, /if \(batch.start_id !== held\) throw new Error/);
  assert.ok(reconcile.indexOf("writeManagedBatch(batch.batch_id)") < reconcile.indexOf("applyBatchSnapshot(snapshot, catalog)"));
  assert.ok(reconcile.indexOf("writeManagedBatch(batch.batch_id)") < reconcile.indexOf("if (batch.outcome == null)"));
});
