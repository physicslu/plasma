import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("app/plasma-api.ts"), "utf8");

test("Web JobState contract includes infrastructure error", () => {
  assert.match(source, /\|\s*"error"/);
});

test("infrastructure error is terminal for Manager Batch activity tracking", () => {
  const batchSnapshot = fs.readFileSync(path.resolve("app/batch-snapshot.ts"), "utf8");
  const terminalSet = batchSnapshot.match(/export const terminalServerBatchStates = new Set<ServerBatchState>\(\[([\s\S]*?)\]\);/);
  assert.ok(terminalSet, "terminal Batch state set must remain explicit");
  assert.match(terminalSet[1], /"error"/);
});

test("Job snapshots expose retry provenance for future Batch policy", () => {
  assert.match(source, /attempt_history\?: JobAttempt\[\]/);
  assert.match(source, /retry_exhausted\?: boolean/);
  assert.match(source, /failure_source\?: string \| null/);
});

test("plasma-api is a type module: the Browser issues no direct PPU Job (U10)", () => {
  assert.doesNotMatch(source, /fetch\(|export (async )?function|directBrowserExecutionOwnerId|execution_owner_id/);
  assert.match(source, /export class PlasmaApiError extends Error/);
});
