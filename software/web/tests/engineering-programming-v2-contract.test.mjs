import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Engineering Programming uses the approved status-first single-PPU workflow", async () => {
  const page = await source("../app/engineering/page.tsx");
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const refresh = await source("../app/engineering/engineering-workspace-refresh.css");

  assert.match(page, /ProgrammingWorkspaceV2/);
  assert.match(workspace, /SINGLE PPU PROGRAMMING/);
  assert.match(workspace, /SYSTEM SETUP &amp; TARGETING/);
  assert.match(workspace, /PROGRAMMING JOB/);
  assert.match(workspace, /Target IC/);
  assert.match(workspace, /Programming Image/);
  assert.match(workspace, /START PROGRAMMING/);
  assert.match(workspace, /LIVE SITE STATUS/);
  assert.match(workspace, /aria-label=\{`\$\{setupCollapsed \? "Expand" : "Collapse"\} System Setup`\}/);
  assert.match(workspace, /aria-label=\{`\$\{programmingJobCollapsed \? "Expand" : "Collapse"\} Programming Job`\}/);
  assert.match(workspace, /programmingJobCollapsed \? "is-collapsed" : ""/);
  assert.doesNotMatch(workspace, /TARGET SITES/);
  assert.doesNotMatch(workspace, /LIVE PROGRESS MONITOR/);

  assert.match(refresh, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(refresh, /1\. SYSTEM SETUP/);
  assert.match(refresh, /2\. PROGRAMMING JOB/);
  assert.match(refresh, /3\. LIVE SITE STATUS/);
  assert.match(refresh, /\.engineeringProgrammingV2 \.recentEvents\s*\{[\s\S]*display:\s*none !important/);
});

test("Engineering shell uses the approved dark EMode sidebar and supports collapse", async () => {
  const page = await source("../app/engineering/page.tsx");
  const refresh = await source("../app/engineering/engineering-workspace-refresh.css");

  assert.match(page, /engineeringSidebar/);
  assert.match(page, />EMode</);
  assert.match(page, /Collapse Engineering menu/);
  assert.match(page, /Expand Engineering menu/);
  assert.match(page, /sidebarCollapsed/);
  assert.match(refresh, /linear-gradient\(180deg, #17283a/);
  assert.match(refresh, /\.engineeringPage\.sidebarCollapsed \.engineeringWorkspace/);
});

test("LIVE SITE STATUS owns Batch Site selection while keeping every PPU Site visible", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /aria-label="Engineering Site selection"/);
  assert.match(workspace, /aria-label="Select all Engineering batch Sites"/);
  assert.match(workspace, /aria-label=\{`Batch select SITE \$\{site\.id\}`\}/);
  assert.match(workspace, /\{sites\.map\(site => \{/);
  assert.doesNotMatch(workspace, /\{selectedSites\.map\(site => \{/);
  assert.match(workspace, /const siteIds = \[\.\.\.selectedSiteIds\];/);
  assert.match(workspace, /disabled=\{batchRunning \|\| !site\.enabled \|\| isRunning\(site\)\}/);
});

test("Engineering Batch Summary uses server Batch manufacturing outcomes and Production KPI vocabulary", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /title="BATCH SUMMARY"/);
  for (const label of ["SITES", "TOTAL IC", "PROCESSED IC", "PASS", "FAIL", "YIELD", "BATCH TIME"]) {
    assert.match(workspace, new RegExp(`label: "${label}"`));
  }
  assert.match(workspace, /const previewTotalIc = selectedSiteIds\.length \* \(repeatValue \?\? 0\)/);
  assert.match(workspace, /const batchManufacturing = useMemo\(\(\) => \{/);
  assert.match(workspace, /site\.completed_rounds/);
  assert.match(workspace, /site\.final_failures/);
  assert.match(workspace, /totalIc: batchSnapshot\.sites\.length \* batchSnapshot\.execution_policy\.repeat_count/);
  assert.match(workspace, /const completedIc = displayedBatch\.pass \+ displayedBatch\.fail/);
  assert.match(workspace, /label: "PROCESSED IC", value: completedIc/);
  assert.doesNotMatch(workspace, /CYCLE TIME/);
});

test("Production and Engineering use the same named Batch Summary primitive", async () => {
  const production = await source("../app/fleet/factory-console-v2.tsx");
  const engineering = await source("../app/engineering/programming-workspace-v2.tsx");
  const operatorPanel = await source("../app/operator-ui/operator-panel.tsx");

  assert.match(operatorPanel, /operatorKpiSummaryHeader/);
  assert.match(production, /ariaLabel="Production Batch Summary"/);
  assert.match(production, /title="BATCH SUMMARY"/);
  assert.match(engineering, /ariaLabel="Engineering Batch Summary"/);
  assert.match(engineering, /title="BATCH SUMMARY"/);
});

test("Engineering keeps direct single-Site jobs separate from server-owned Batch execution", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const controller = await source("../app/engineering/engineering-server-batch.ts");

  assert.match(workspace, /startJob\(/);
  assert.match(workspace, /cancelJob\(/);
  assert.match(workspace, /startEngineeringServerBatch\(/);
  assert.match(workspace, /restoreEngineeringServerBatch\(/);
  assert.match(workspace, /abortEngineeringServerBatch\(/);
  assert.match(controller, /createServerBatch\(/);
  assert.match(controller, /getServerBatch\(/);
  assert.match(controller, /cancelServerBatch\(/);
});

test("Engineering Target IC is optional and crosses both direct-Job and server-Batch boundaries", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const api = await source("../app/plasma-api.ts");
  const batchApi = await source("../app/server-batch-api.ts");

  assert.match(workspace, /ICPickerField/);
  assert.match(workspace, /targetDevice:\s*targetDevice\s*\?/);
  assert.match(api, /targetDevice\?:\s*JobTargetDeviceRequest/);
  assert.match(api, /body\.target_device\s*=/);
  assert.match(api, /engineeringTarget\s*&&\s*options\.targetDevice/);
  assert.match(batchApi, /targetDevice\?:\s*BatchTargetDeviceRequest/);
  assert.match(batchApi, /target_device:\s*options\.targetDevice/);
});

test("Engineering retains explicit Retry while the former Production single-PPU route is retired", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const retiredProductionRoute = await source("../app/fleet/programming/page.tsx");

  assert.match(workspace, /Site Retry Limit/);
  assert.match(workspace, /useState\("3"\)/);
  assert.match(retiredProductionRoute, /redirect\("\/fleet"\)/);
});

test("Engineering v2 advertises only the implemented binary Programming Image normalizer", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /accept="\.bin,application\/octet-stream"/);
  assert.match(workspace, /Programming Image \(\.bin\)/);
  assert.doesNotMatch(workspace, /\.hex/);
});

test("Engineering v2 retains per-Site cancellation, polling and full audit evidence", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /Cancel SITE \$\{site\.id\}/);
  assert.match(workspace, /window\.setTimeout\(poll, POLL_INTERVAL_MS\)/);
  assert.match(workspace, /EngineeringLogPanel/);
  assert.match(workspace, /CACHE CHECK/);
  assert.match(workspace, /\[TARGET\] RESTORED/);
});
