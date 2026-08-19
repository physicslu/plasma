import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps per-Site cancel intent authoritative across operation-completion races", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const lifecycle = await readFile(new URL("../app/batch-lifecycle.ts", import.meta.url), "utf8");

  assert.match(lifecycle, /cancelRequested\?: boolean/);
  assert.match(lifecycle, /isCancelRequested\(siteId: number\)/);
  assert.match(lifecycle, /cancelSite\(siteId: number\): string \| undefined/);
  assert.match(lifecycle, /this\.commands\[siteId\] = \{ \.\.\.command, cancelRequested: true \}/);
  assert.match(lifecycle, /return this\.isCancelRequested\(siteId\)/);

  assert.match(page, /lifecycle\.cancelSite\(siteId\)/);
  assert.match(page, /lifecycle\.isCancelRequested\(siteId\)/);
  assert.match(page, /Cancel requested · next batch operation suppressed/);
  assert.match(page, /await requestJobCancel\(siteId, activeJobId, false\)/);
  assert.doesNotMatch(
    page,
    /const cancelWasRequested = lifecycle\.cancelRequested \|\| cancelRequests\.current\.has\(job\.job_id\)/,
  );

  const siteCancel = page.indexOf("const activeJobId = lifecycle.cancelSite(siteId)");
  const cancellingUi = page.indexOf('setBatchSiteState(siteId, "cancelling")', siteCancel);
  const backendCancel = page.indexOf("await requestJobCancel(siteId, activeJobId, false)", siteCancel);
  assert.notEqual(siteCancel, -1, "per-Site lifecycle cancel barrier is missing");
  assert.notEqual(cancellingUi, -1, "per-Site cancelling UI transition is missing");
  assert.notEqual(backendCancel, -1, "active batch job cancellation is missing");
  assert.ok(siteCancel < cancellingUi, "workflow cancel intent must be recorded before UI cancellation state");
  assert.ok(siteCancel < backendCancel, "workflow cancel intent must be recorded before backend cancellation");
});

test("keeps global batch cancellation distinct from per-Site cancellation", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const lifecycle = await readFile(new URL("../app/batch-lifecycle.ts", import.meta.url), "utf8");

  assert.match(lifecycle, /private cancelBarrier = false/);
  assert.match(lifecycle, /cancel\(\): BatchCancelSnapshot/);
  assert.match(lifecycle, /this\.cancelBarrier = true/);
  assert.match(page, /const \{ submittingSites, activeJobs \} = lifecycle\.cancel\(\)/);
  assert.match(page, /: lifecycle\.cancelRequested\s*\? "CANCELLED"/);
  assert.match(page, /cancelledSiteIds\.length\s*\? "PARTIAL"/);
});
