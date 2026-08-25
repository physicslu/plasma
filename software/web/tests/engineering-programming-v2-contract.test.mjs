import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Engineering Programming uses the approved status-first single-PPU workflow", async () => {
  const page = await source("../app/engineering/page.tsx");
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(page, /ProgrammingWorkspaceV2/);
  assert.match(workspace, /SINGLE PPU PROGRAMMING/);
  assert.match(workspace, /SYSTEM SETUP &amp; TARGETING/);
  assert.match(workspace, /PROGRAMMING JOB/);
  assert.match(workspace, /Target IC/);
  assert.match(workspace, /Programming Image/);
  assert.match(workspace, /START PROGRAMMING/);
  assert.match(workspace, /LIVE SITE STATUS/);
  assert.match(workspace, /RECENT EVENTS/);
  assert.doesNotMatch(workspace, /TARGET SITES/);
  assert.doesNotMatch(workspace, /LIVE PROGRESS MONITOR/);
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

test("Engineering KPI separates PPU topology from Batch membership", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /<small>PPU SITES<\/small>/);
  assert.match(workspace, /<small>SELECTED<\/small>/);
  assert.doesNotMatch(workspace, /<small>TOTAL IC<\/small>/);
});

test("Engineering Programming keeps direct PPU jobs rather than borrowing Production server Batch ownership", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /startJob\(/);
  assert.match(workspace, /cancelJob\(/);
  assert.doesNotMatch(workspace, /createServerBatch/);
  assert.doesNotMatch(workspace, /ServerBatchSnapshot/);
});

test("Engineering Target IC is optional but a selected catalog record is sent to the direct job boundary", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const api = await source("../app/plasma-api.ts");

  assert.match(workspace, /ICPickerField/);
  assert.match(workspace, /targetDevice:\s*targetDevice\s*\?/);
  assert.match(api, /targetDevice\?:\s*JobTargetDeviceRequest/);
  assert.match(api, /body\.target_device\s*=/);
  assert.match(api, /engineeringTarget\s*&&\s*options\.targetDevice/);
});

test("Engineering policy preserves explicit Retry while Production remains compact", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");
  const production = await source("../app/fleet/programming/production-programming-page.tsx");

  assert.match(workspace, /Site Retry Limit/);
  assert.match(workspace, /useState\("3"\)/);
  assert.doesNotMatch(production, /Site Retry Limit/);
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
