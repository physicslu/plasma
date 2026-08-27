import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("app/plasma-api.ts"), "utf8");

test("Web JobState contract includes infrastructure error", () => {
  assert.match(source, /\|\s*"error"/);
});

test("infrastructure error is terminal for execution activity tracking", () => {
  const terminalSet = source.match(/const terminalJobStates = new Set<JobState>\(\[([\s\S]*?)\]\);/);
  assert.ok(terminalSet, "terminal JobState set must remain explicit");
  assert.match(terminalSet[1], /"error"/);
});

test("Job snapshots expose retry provenance for future Batch policy", () => {
  assert.match(source, /attempt_history\?: JobAttempt\[\]/);
  assert.match(source, /retry_exhausted\?: boolean/);
  assert.match(source, /failure_source\?: string \| null/);
});

test("browser direct jobs carry a page-instance execution owner", () => {
  assert.match(source, /let directBrowserExecutionOwnerId: string \| null = null/);
  assert.match(source, /directBrowserExecutionOwnerId = window\.crypto\.randomUUID\(\)/);
  assert.match(
    source,
    /execution_owner_id: options\.executionOwnerId \?\? browserExecutionOwnerId\(\)/,
  );
});
