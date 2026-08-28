import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readabilityPath = new URL("../app/engineering/engineering-readability.css", import.meta.url);
const refreshPath = new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url);
const sharedControlsPath = new URL("../app/operator-ui/programming-job-controls.css", import.meta.url);
const designContractPath = new URL("../app/operator-ui/operator-design-contract.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering readability owns only Engineering targeting and live Site typography", async () => {
  const [css, sharedControls, designContract] = await Promise.all([
    source(readabilityPath),
    source(sharedControlsPath),
    source(designContractPath),
  ]);

  for (const contract of [
    ".liveSiteStatus > header > span::before {\n  font-size: 12px;",
    ".workflowField,\n.engineeringProgrammingV2 .workflowField select {\n  font-size: 11px;",
    ".workflowField > span {\n  font-size: 12px;",
    ".topologyFoot {\n  font-size: 10px;",
    ".channelTable {\n  font-size: 12px;",
    ".channelTable th {\n  font-size: 10px;",
    ".channelTable td:nth-child(2) b {\n  font-size: 13px;",
    ".channelTable .state {\n  font-size: 10px;",
  ]) {
    assert.ok(css.includes(contract), `missing readability contract: ${contract}`);
  }

  for (const forbidden of [
    ".programmingJob",
    ".jobRow",
    ".imageField",
    ".engineeringBrowseButton",
    ".engineeringImageHint",
    ".engineeringPolicyRow",
    ".engineeringRetryField",
    ".programmingBatchOperations",
    ".batchReadiness {",
    ".programmingActions button",
  ]) {
    assert.equal(css.includes(forbidden), false, `Engineering readability must not own retired/shared Programming selector: ${forbidden}`);
  }

  assert.match(sharedControls, /\.programmingJobOperationChecks label\s*\{[\s\S]*font-size:\s*var\(--operator-control-font-size\)[\s\S]*font-weight:\s*550/);
  assert.match(sharedControls, /\.programmingJobStart,[\s\S]*\.programmingJobAbort\s*\{[\s\S]*font-size:\s*var\(--operator-action-font-size\)[\s\S]*font-weight:\s*800/);
  assert.match(designContract, /--operator-control-font-size:\s*10px/);
  assert.match(designContract, /--operator-action-font-size:\s*11px/);
  assert.doesNotMatch(
    css,
    /operatorKpiStrip|batchSummary(?:Header|Grid)|data-kpi=/,
    "Batch Summary typography must stay with the shared component",
  );
});

test("Engineering System Setup label rewrite does not own Programming Job presentation", async () => {
  const [css, refresh] = await Promise.all([source(readabilityPath), source(refreshPath)]);

  assert.match(refresh, /\.engineeringProgrammingV2 \.targetingCard > header\s*\{[\s\S]*font-size:\s*0/);
  assert.ok(css.includes(".targetingCard > header::before,"));
  assert.doesNotMatch(
    `${css}\n${refresh}`,
    /\.programmingJob(?:Panel|Card|Grid|Field|ActionBar|Status|OperationChecks|PolicyControls)\b/,
    "Engineering styles must not own shared Programming Job presentation",
  );
});

test("Engineering readability layer is typography-only and loads after layout CSS", async () => {
  const [css, page] = await Promise.all([source(readabilityPath), source(pagePath)]);

  for (const forbidden of [
    "grid-template",
    "grid-column",
    "grid-row",
    "display:",
    "width:",
    "height:",
    "padding:",
    "margin:",
    "gap:",
    "position:",
  ]) {
    assert.equal(css.includes(forbidden), false, `readability layer must not own layout property ${forbidden}`);
  }

  const refresh = page.indexOf('import "./engineering-workspace-refresh.css";');
  const readability = page.indexOf('import "./engineering-readability.css";');
  assert.ok(refresh >= 0 && readability > refresh, "readability CSS must load after the approved Engineering layout CSS");
});
