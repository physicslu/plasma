import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const shared = fs.readFileSync(new URL("../app/batch-dashboard-panels.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/batch-dashboard-panels.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/server-batch-page.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/server-batch.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace.tsx", import.meta.url), "utf8");
const serverBatchApi = fs.readFileSync(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");
const snapshotStore = fs.readFileSync(new URL("../app/server-batch-snapshot-store.ts", import.meta.url), "utf8");

test("Pmod owns the shared topology KPI summary while Emode keeps shared policy and live Site semantics", () => {
  assert.match(pmod, /BatchTopologySummary/);
  assert.match(pmod, /unifiedBatchControlStack/);
  assert.match(pmod, /ActiveFpsSummary/);
  assert.match(pmod, /BatchPolicyPanel/);

  assert.doesNotMatch(emode, /BatchTopologySummary/);
  assert.match(emode, /engineeringProgrammingKpis/);
  assert.match(emode, /unifiedBatchControlStack/);
  assert.match(emode, /ActiveFpsSummary/);
  assert.match(emode, /BatchPolicyPanel/);
});

test("shared top summary prioritizes production KPIs while keeping topology context", () => {
  assert.match(shared, /data-topology-context="facilities"/);
  assert.match(shared, /data-topology-context="ppus"/);
  assert.match(shared, /data-topology-context="sites"/);
  assert.match(shared, /data-production-kpi="total"/);
  assert.match(shared, /data-production-kpi="pass"/);
  assert.match(shared, /data-production-kpi="fail"/);
  assert.match(shared, /data-production-kpi="yield"/);
  assert.match(shared, /<small>Total IC<\/small>/);
  assert.match(shared, /<small>PASS<\/small>/);
  assert.match(shared, /<small>FAIL<\/small>/);
  assert.match(shared, /<small>Yield<\/small>/);
});

test("Production KPI authority is the latest server Batch snapshot", () => {
  assert.match(snapshotStore, /latestSnapshot/);
  assert.match(snapshotStore, /publishServerBatchSnapshot/);
  assert.match(snapshotStore, /subscribeServerBatchSnapshot/);
  assert.match(serverBatchApi, /publishServerBatchSnapshot/);
  assert.equal((serverBatchApi.match(/return observeBatchSnapshot\(payload\.batch\);/g) ?? []).length, 4);
  assert.match(shared, /useSyncExternalStore/);
  assert.match(shared, /window\.location\.pathname === "\/fleet"/);
  assert.match(shared, /site\.completed_rounds/);
  assert.match(shared, /site\.final_failures/);
  assert.match(shared, /const total = pass \+ fail/);
  assert.match(shared, /data-kpi-source=\{productionBatch \? "server-batch-snapshot" : "local-projection"\}/);
});

test("shared Active FPS summary exposes only selected, running and stopped Site counts", () => {
  assert.match(shared, /data-summary-unit="site"/);
  assert.match(shared, /Active FPS · SITE STATUS/);
  assert.match(shared, /const stoppedSiteCount = counts\.pass \+ counts\.faulted \+ counts\.error \+ counts\.stopped \+ counts\.cancelled/);
  assert.match(shared, /\["selected", "TOTAL SELECTED SITES", counts\.selected\]/);
  assert.match(shared, /\["running", "RUNNING SITES", counts\.running\]/);
  assert.match(shared, /\["terminal", "STOPPED SITES", stoppedSiteCount\]/);
  assert.match(shared, /repeat\(auto-fit, minmax\(110px, 1fr\)\)/);
  assert.equal((shared.match(/\["(?:selected|running|terminal)",/g) ?? []).length, 3);
});

test("Engineering Batch Details retain the full Site terminal breakdown", () => {
  assert.match(shared, /<small>PASSED SITES<\/small>/);
  assert.match(shared, /<small>FAULTED SITES<\/small>/);
  assert.match(shared, /<small>ERROR SITES<\/small>/);
  assert.match(shared, /<small>STOPPED SITES<\/small>/);
  assert.match(shared, /<small>CANCELLED SITES<\/small>/);
});

test("policy controls expose hover/focus help, canonical ranges, and default Retry 3", () => {
  assert.match(shared, /role="tooltip"/);
  assert.match(shared, /DEFAULT_SITE_RETRY_LIMIT = "3"/);
  assert.match(shared, /aria-label="Repeat Count" type="number" min="1" max="10000"/);
  assert.match(shared, /aria-label="Site Retry Limit" type="number" min="0" max="20"/);
  assert.match(shared, /aria-label="Failed Site Stop Threshold"/);
  assert.match(emode, /useState\("3"\)/);
});

test("shared Batch policy remains collapsible for legacy dashboard consumers", () => {
  assert.match(shared, /const \[controlExpanded, setControlExpanded\] = useState\(true\)/);
  assert.match(shared, /PROGRAMMING \/ BATCH CONTROL/);
  assert.match(shared, /aria-expanded=\{controlExpanded\}/);
  assert.match(shared, /data-control-expanded=\{controlExpanded \? "true" : "false"\}/);
  assert.match(shared, /stack\.dataset\.collapsed = controlExpanded \? "false" : "true"/);
  assert.match(sharedCss, /\.unifiedBatchControlStack\[data-collapsed="true"\]\s*>\s*\.programmingBatchToolbar\s*\{[^}]*display:\s*none;/s);
  assert.match(sharedCss, /\.batchControlPanelHeader/);
  assert.match(sharedCss, /\.batchControlPanelToggle/);
});

test("Batch diagnostics stay off P Mode and are available to Engineering consumers", () => {
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
