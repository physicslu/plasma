import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const shared = fs.readFileSync(new URL("../app/batch-dashboard-panels.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/batch-dashboard-panels.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/server-batch-page.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/server-batch.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace.tsx", import.meta.url), "utf8");

test("Pmod and Emode share the same three upper Batch dashboard primitives", () => {
  for (const source of [pmod, emode]) {
    assert.match(source, /BatchTopologySummary/);
    assert.match(source, /unifiedBatchControlStack/);
    assert.match(source, /ActiveFpsSummary/);
    assert.match(source, /BatchPolicyPanel/);
  }
});

test("shared top summary prioritizes production KPIs while keeping topology context", () => {
  assert.match(shared, /data-topology-context="facilities"/);
  assert.match(shared, /data-topology-context="ppus"/);
  assert.match(shared, /data-topology-context="sites"/);
  assert.match(shared, /data-production-kpi="total"/);
  assert.match(shared, /data-production-kpi="pass"/);
  assert.match(shared, /data-production-kpi="fail"/);
  assert.match(shared, /data-production-kpi="yield"/);
  assert.match(shared, /const totalIc = counts\.selected/);
  assert.match(shared, /const failedIc = counts\.faulted/);
  assert.match(shared, /counts\.pass \/ totalIc/);
  assert.match(shared, /<small>Total IC<\/small>/);
  assert.match(shared, /<small>PASS<\/small>/);
  assert.match(shared, /<small>FAIL<\/small>/);
  assert.match(shared, /<small>Yield<\/small>/);
});

test("shared Active FPS summary keeps FAULTED and ERROR distinct without duplicate error state", () => {
  assert.match(shared, /\["faulted", copy\.faulted, counts\.faulted\]/);
  assert.match(shared, /\["error", copy\.error, counts\.error\]/);
  assert.equal((shared.match(/data-active-fps-state/g) ?? []).length, 1);
  assert.match(shared, /selected.*running.*pass.*faulted.*error.*stopped.*cancelled/s);
});

test("policy controls expose hover/focus help, canonical ranges, and default Retry 3", () => {
  assert.match(shared, /role="tooltip"/);
  assert.match(shared, /DEFAULT_SITE_RETRY_LIMIT = "3"/);
  assert.match(shared, /aria-label="Repeat Count" type="number" min="1" max="10000"/);
  assert.match(shared, /aria-label="Site Retry Limit" type="number" min="0" max="20"/);
  assert.match(shared, /aria-label="Failed Site Stop Threshold"/);
});

test("Batch diagnostics stay off P Mode and are expandable in E Mode", () => {
  assert.match(pmodCss, /\.productionMainPanel\s*>\s*\.serverBatchStatistics\s*\{[^}]*display:\s*none;/s);
  assert.match(shared, /<details className="engineeringBatchDetails">/);
  assert.match(shared, /<summary>Batch Details<\/summary>/);
  assert.match(sharedCss, /\.engineeringBatchDetails\s*\{\s*display:\s*none;/s);
  assert.match(sharedCss, /\.engineeringProgramming\s+\.engineeringBatchDetails\s*\{[^}]*display:\s*block;/s);
});

test("Emode policy is behavioral rather than decorative", () => {
  assert.match(emode, /for \(let round = 1; round <= repeatValue; round \+= 1\)/);
  assert.match(emode, /for \(let attempt = 0; attempt <= retryValue; attempt \+= 1\)/);
  assert.match(emode, /terminalize\(siteId, "faulted"/);
  assert.match(emode, /terminalize\(siteId, "error"/);
  assert.match(emode, /batchStopReason\.current = "threshold"/);
});
