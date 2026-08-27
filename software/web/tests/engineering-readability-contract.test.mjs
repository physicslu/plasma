import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readabilityPath = new URL("../app/engineering/engineering-readability.css", import.meta.url);
const refreshPath = new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url);
const sharedControlsPath = new URL("../app/operator-ui/programming-job-controls.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering readability layer raises the approved operator font floor without overriding shared Programming controls", async () => {
  const [css, sharedControls] = await Promise.all([source(readabilityPath), source(sharedControlsPath)]);

  for (const contract of [
    ".liveSiteStatus > header > span::before {\n  font-size: 12px;",
    ".workflowField select,\n.engineeringProgrammingV2 .jobRow,",
    ".workflowField > span {\n  font-size: 12px;",
    ".jobRow > strong {\n  font-size: 12px;",
    ".engineeringImageHint {\n  font-size: 9px;",
    ".engineeringRetryField {\n  font-size: 10px;",
    ".channelTable {\n  font-size: 12px;",
    ".channelTable th {\n  font-size: 10px;",
    ".channelTable td:nth-child(2) b {\n  font-size: 13px;",
    ".channelTable .state {\n  font-size: 10px;",
  ]) {
    assert.ok(css.includes(contract), `missing readability contract: ${contract}`);
  }

  for (const forbidden of [
    ".programmingBatchOperations .operationChecks label",
    ".batchReadiness {",
    ".programmingActions button",
  ]) {
    assert.equal(css.includes(forbidden), false, `Engineering readability must not override shared Programming control: ${forbidden}`);
  }

  assert.match(sharedControls, /font-size:\s*9px[\s\S]*font-weight:\s*700/);
  assert.match(sharedControls, /\.programmingActions \.startProgramming,[\s\S]*font-size:\s*10px[\s\S]*font-weight:\s*850/);
  assert.doesNotMatch(
    css,
    /operatorKpiStrip|batchSummary(?:Header|Grid)|data-kpi=/,
    "Batch Summary typography must stay with the shared component",
  );
});

test("Engineering canonical card headers do not render their legacy text twice", async () => {
  const [css, refresh] = await Promise.all([source(readabilityPath), source(refreshPath)]);

  assert.equal(
    css.includes(".engineeringProgrammingV2 .productionProgrammingCard > header,"),
    false,
    "readability CSS must not revive raw card header text",
  );
  assert.ok(
    refresh.includes(".engineeringProgrammingV2 .targetingCard > header,\n.engineeringProgrammingV2 .programmingJobCard > header {\n  font-size: 0;"),
    "raw SYSTEM SETUP / PROGRAMMING JOB header text must remain hidden",
  );
  assert.ok(css.includes(".targetingCard > header::before,"));
  assert.ok(css.includes(".programmingJobCard > header::before,"));
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
