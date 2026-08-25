import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readabilityPath = new URL("../app/engineering/engineering-readability.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering readability layer raises the approved operator font floor", async () => {
  const css = await source(readabilityPath);

  for (const contract of [
    ".productionProgrammingKpis small {\n  font-size: 10px;",
    ".liveSiteStatus > header > span::before {\n  font-size: 12px;",
    ".workflowField select,\n.engineeringProgrammingV2 .jobRow,",
    ".jobRow > strong {\n  font-size: 11px;",
    ".engineeringImageHint {\n  font-size: 9px;",
    ".programmingBatchOperations .operationChecks label,",
    ".engineeringRetryField {\n  font-size: 10px;",
    ".batchReadiness {\n  font-size: 10px;",
    ".programmingActions button {\n  font-size: 12px;",
    ".channelTable {\n  font-size: 12px;",
    ".channelTable th {\n  font-size: 10px;",
    ".channelTable .state {\n  font-size: 10px;",
  ]) {
    assert.ok(css.includes(contract), `missing readability contract: ${contract}`);
  }
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
