import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

// U10: EMode Programming is the Manager-managed workspace only. The standalone
// Programming Workspace v2 (direct PPU Jobs, PPU-local server Batch, per-Site
// Job cancel) is retired; these contracts hold for the managed workspace.

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

const WORKSPACE = "../app/engineering/managed-programming-workspace.tsx";

test("Engineering Programming uses the approved status-first single-PPU workflow", async () => {
  const page = await source("../app/engineering/page.tsx");
  const workspace = await source(WORKSPACE);
  const sharedJob = await source("../app/operator-ui/programming-job-panel.tsx");
  const sharedPanel = await source("../app/operator-ui/operator-panel.tsx");
  const refresh = await source("../app/engineering/engineering-workspace-refresh.css");

  assert.match(page, /<ManagedProgrammingWorkspace \/>/);
  assert.match(workspace, /SINGLE PPU PROGRAMMING/);
  assert.match(workspace, /title="SYSTEM SETUP & TARGETING"/);
  assert.match(workspace, /PROGRAMMING JOB/);
  assert.match(workspace, /Target IC/);
  assert.match(workspace, /Programming Image/);
  assert.match(workspace, /START PROGRAMMING/);
  assert.match(workspace, /LIVE SITE STATUS/);
  assert.match(workspace, /aria-label=\{`\$\{setupCollapsed \? "Expand" : "Collapse"\} System Setup`\}/);
  assert.match(workspace, /<ProgrammingJobPanel[\s\S]*mode="engineering"/);
  assert.match(workspace, /collapsed=\{jobCollapsed\}/);
  assert.match(sharedJob, /<OperatorPanelToggle/);
  assert.match(sharedPanel, /export function OperatorPanelToggle/);
  assert.match(sharedPanel, /aria-expanded=\{expanded\}/);
  assert.doesNotMatch(sharedJob, /programmingJobCollapseButton/);
  assert.doesNotMatch(workspace, /TARGET SITES/);
  assert.doesNotMatch(workspace, /LIVE PROGRESS MONITOR/);
  assert.doesNotMatch(workspace, /RECENT EVENTS|recentEvents|Engineering recent events/);
  assert.doesNotMatch(refresh, /recentEvents/);

  assert.match(refresh, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  // Section numbers come from the shared OperatorPanelHeader, never from CSS
  // generated content, and both modes use the same chapter order.
  assert.match(workspace, /<OperatorPanelHeader\s+number=\{1\}\s+title="SYSTEM SETUP & TARGETING"/);
  assert.match(workspace, /<OperatorPanelHeader\s+number=\{3\}\s+title="LIVE SITE STATUS"/);
  assert.match(sharedJob, /const fieldNumber = \(index: number\) => `\$\{PROGRAMMING_JOB_SECTION\}-\$\{index\}\.`/);
  assert.doesNotMatch(refresh, /targetingCard > header::before|liveSiteStatus > header > span::before|font-size:\s*0/);
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
  const workspace = await source(WORKSPACE);

  assert.match(workspace, /aria-label="Engineering Site selection"/);
  assert.match(workspace, /aria-label=\{`Select SITE \$\{site\.site_id\} for programming`\}/);
  // Every Site the Manager Fleet reports is a row, selected or not.
  assert.match(workspace, /\{\(ppu\?\.sites \?\? \[\]\)\.map\(site => \{/);
  assert.match(workspace, /const started = \[\.\.\.siteIds\];/);
  assert.match(workspace, /disabled=\{active \|\| !capability\?\.programmable\}/);
});

test("Engineering Batch Summary uses Manager Batch statistics and Production KPI vocabulary", async () => {
  const workspace = await source(WORKSPACE);
  const statistics = await source("../app/programming/batch-statistics.ts");

  assert.match(workspace, /title="BATCH SUMMARY"/);
  for (const label of ["SITES", "TOTAL IC", "PROCESSED IC", "PASS IC", "FAIL IC", "YIELD", "BATCH TIME"]) {
    assert.match(statistics, new RegExp(`label: "${label}"`));
  }
  assert.match(workspace, /\? managedBatchStatistics\(batch\)/);
  assert.match(workspace, /const kpis = statisticsKpis\(statistics, formatElapsed\(elapsed\)\);/);
  assert.doesNotMatch(workspace, /CYCLE TIME/);
});

test("Production and Engineering use the same Batch Summary and shared Panel Header primitives", async () => {
  const production = await source("../app/fleet/factory-console-v2.tsx");
  const engineering = await source(WORKSPACE);
  const batchSummary = await source("../app/operator-ui/batch-summary.tsx");
  const sharedPanel = await source("../app/operator-ui/operator-panel.tsx");

  assert.match(batchSummary, /import \{ OperatorPanelHeader \} from "\.\/operator-panel"/);
  assert.match(batchSummary, /<OperatorPanelHeader title=\{title\} meta=\{meta\} \/>/);
  assert.match(batchSummary, /className="batchSummaryGrid"/);
  assert.doesNotMatch(batchSummary, /batchSummaryHeader|operatorKpiSummary|operatorKpiStrip/);
  assert.match(sharedPanel, /export function OperatorPanelHeader/);
  assert.match(production, /ariaLabel="Production Batch Summary"/);
  assert.match(production, /title="BATCH SUMMARY"/);
  assert.match(engineering, /ariaLabel="Engineering Batch Summary"/);
  assert.match(engineering, /title="BATCH SUMMARY"/);
});

test("Engineering programming and per-Site READ are separate Manager Batches; the Browser submits no Job", async () => {
  const workspace = await source(WORKSPACE);

  assert.equal((workspace.match(/runManagedBatch\(request, \{/g) ?? []).length, 1);
  assert.match(workspace, /await runManagedRead\(\{ alias, siteId: id, icpn, address, length \}/);
  assert.doesNotMatch(workspace, /startJob\(|cancelJob\(|startEngineeringServerBatch|restoreEngineeringServerBatch|abortEngineeringServerBatch/);
  assert.doesNotMatch(workspace, /createServerBatch|getServerBatch|cancelServerBatch/);
});

test("Engineering Read Memory is an independent per-Site Job, not a Batch operation", async () => {
  const workspace = await source(WORKSPACE);
  const api = await source("../app/engineering/bundle-programming-api.ts");
  const driver = await source("../e2e/tests/programming-job-test-helpers.ts");

  assert.match(api, /export const SEQUENCE_OPERATIONS = \["erase", "program", "verify"\] as const;/);
  assert.match(workspace, /const canRead = routeDeclaring\(routes, icpn, site\.site_id, \["read"\]\) != null;/);
  assert.match(workspace, /aria-label=\{`Read SITE \$\{site\.site_id\} Flash`\}/);
  assert.match(workspace, /Read the whole Flash to a file \(independent Job\)/);
  assert.match(driver, /engineering: \["erase", "program", "verify"\]/);
});

test("Engineering Target IC is required and crosses into the Manager Batch and READ requests", async () => {
  const workspace = await source(WORKSPACE);
  const sharedJob = await source("../app/operator-ui/programming-job-panel.tsx");

  assert.match(sharedJob, /ICPickerField/);
  assert.match(workspace, /targetDevice=\{targetDevice\}/);
  assert.match(workspace, /onTargetChange=\{selectTargetDevice\}/);
  assert.match(workspace, /const icpn = targetDevice\?\.icpn \?\? targetDevice\?\.identifier \?\? null;/);
  assert.match(workspace, /if \(!icpn\) return notReady\("NO TARGET", "Select a Target IC\."\);/);
  assert.match(workspace, /\{ alias: ppu\.alias, siteIds: started, icpn, operations, source, file, \.\.\.policy \}/);
});

test("Engineering retains explicit Retry while the former Production single-PPU route is retired", async () => {
  const workspace = await source(WORKSPACE);
  const retiredProductionRoute = await source("../app/fleet/programming/page.tsx");

  assert.match(workspace, /retryAriaLabel: "Site Retry Limit"/);
  assert.match(workspace, /const \[retryLimit, setRetryLimit\] = useJobSetting\("emode\.retryLimit", 0\);/);
  assert.match(retiredProductionRoute, /redirect\("\/fleet"\)/);
});

test("Engineering advertises only the binary Programming Image or a canonical Bundle", async () => {
  const workspace = await source(WORKSPACE);
  const sharedJob = await source("../app/operator-ui/programming-job-panel.tsx");
  const selector = await source("../app/operator-ui/programming-source-selector.tsx");

  assert.match(sharedJob, /accept=\{image\.accept \?\? "\.bin,application\/octet-stream"\}/);
  assert.match(selector, /image: "\.bin,application\/octet-stream"/);
  assert.match(selector, /bundle: "\.zip,application\/zip"/);
  assert.match(workspace, /accept: PROGRAMMING_SOURCE_ACCEPT\[source\]/);
  assert.match(workspace, /imageLabel="Programming Source"/);
  assert.match(workspace, /Binary Programming Image \(\.bin\)\./);
  assert.doesNotMatch(sharedJob, /\.hex/);
  assert.doesNotMatch(workspace, /\.hex/);
});

test("Engineering READ is whole-region Main Flash and Browser owns no numeric range", async () => {
  const workspace = await source(WORKSPACE);
  const session = await source("../app/workspace-session.tsx");
  const sharedJob = await source("../app/operator-ui/programming-job-panel.tsx");

  // The range is the Programming Route's whole Flash, never Browser input.
  assert.match(workspace, /const address = route\.flash_base;\s*const length = route\.flash_size;/);
  assert.doesNotMatch(workspace, /ENGINEERING_READ_OFFSET|ENGINEERING_READ_LENGTH|readOffset:|readLength:/);
  assert.doesNotMatch(workspace, /Engineering READ offset|Engineering READ length|engineeringReadRow/);
  assert.doesNotMatch(session, /emodeReadOffset|emodeReadLength/);
  assert.doesNotMatch(sharedJob, /compatibilityFields|programmingJobCompatibility/);
});

test("Engineering retains Manager Fleet polling, STOP QUEUING and full audit evidence", async () => {
  const workspace = await source(WORKSPACE);

  assert.match(workspace, /const TOPOLOGY_POLL_MS = 3000;/);
  assert.match(workspace, /timer = setTimeout\(refresh, TOPOLOGY_POLL_MS\)/);
  assert.match(workspace, /onAbort=\{stopQueuing\}/);
  // A running Manager Job is never cancelled from the Browser.
  assert.doesNotMatch(workspace, /Cancel SITE/);
  assert.match(workspace, /EngineeringLogPanel/);
});
