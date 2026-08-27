import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const shared = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const refresh = fs.readFileSync(new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url), "utf8");
const density = fs.readFileSync(new URL("../app/engineering/engineering-density.css", import.meta.url), "utf8");
const readability = fs.readFileSync(new URL("../app/engineering/engineering-readability.css", import.meta.url), "utf8");
const v2 = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");

test("shared Programming Job contract owns one PMode-derived desktop composition", () => {
  assert.match(shared, /\.factoryActionBar,[\s\S]*\.engineeringProgrammingV2 \.programmingJobCard \.programmingActions/);
  assert.match(shared, /grid-template-columns:\s*minmax\(0, 1fr\) 160px minmax\(0, 1fr\)/);
  assert.match(shared, /\.factoryBatchStatus,[\s\S]*\.engineeringProgrammingV2 \.programmingJobCard \.batchReadiness/);
  assert.match(shared, /height:\s*34px/);
  assert.match(shared, /width:\s*14px/);
  assert.match(shared, /min-height:\s*38px/);
});

test("Engineering responsive layers cannot reintroduce a second operation/action presentation", () => {
  assert.doesNotMatch(refresh, /\.programmingBatchOperations \.operationChecks\s*\{/);
  assert.doesNotMatch(refresh, /\.programmingBatchOperations \.operationChecks label\s*\{/);
  assert.doesNotMatch(refresh, /\.programmingActions\s*button\s*\{/);
  assert.doesNotMatch(refresh, /\.programmingJobBody\s*>\s*\.batchReadiness\s*\{/);
  assert.doesNotMatch(refresh, /grid-template-columns:\s*minmax\(0, 1fr\) minmax\(140px, \.55fr\)/);

  assert.doesNotMatch(readability, /\.programmingBatchOperations \.operationChecks label/);
  assert.doesNotMatch(readability, /\.programmingActions button/);
  assert.doesNotMatch(readability, /\.batchReadiness\s*\{/);

  assert.doesNotMatch(density, /> \.batchReadiness\s*\{/);
  assert.doesNotMatch(density, /grid-template-columns:\s*minmax\(0, 1fr\) 180px minmax\(0, 1fr\)/);
  assert.doesNotMatch(density, /> \.programmingActions > button/);

  assert.doesNotMatch(v2, /\.batchReadiness\s*\{/);
  assert.doesNotMatch(v2, /\.programmingActions\s*\{/);
});
