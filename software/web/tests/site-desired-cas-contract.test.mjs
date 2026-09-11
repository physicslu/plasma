import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const siteUi = await readFile(new URL("../app/engineering/ppu-site-desired-configuration-core.tsx", import.meta.url), "utf8");
const registryApi = await readFile(new URL("../app/engineering/ppu-registry-api.ts", import.meta.url), "utf8");
const managerBff = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");

test("Site desired writes carry an explicit deterministic revision precondition", () => {
  assert.match(registryApi, /desired_revision: string/);
  assert.match(registryApi, /expectedRevision: string/);
  assert.match(registryApi, /\^sha256:\[0-9a-f\]\{64\}\$/);
  assert.match(registryApi, /"If-Match": `"\$\{expectedRevision\}"`/);
  assert.match(managerBff, /"If-Match"/);
});

test("dirty Drafts retain their baseline revision while polling refreshes clean rows", () => {
  assert.match(siteUi, /baselineRevisions/);
  assert.match(siteUi, /!dirtyRef\.current\.has\(site\.site_id\).*site\.desired_revision/s);
  assert.match(siteUi, /expectedRevision = baselineRevisions\[siteId\]/);
  assert.match(siteUi, /saveManagerPpuSite\(alias, siteId, desired, expectedRevision\)/);
});

test("stale Draft conflicts fail closed and require explicit operator reconciliation", () => {
  assert.match(siteUi, /requestError\.status === 412/);
  assert.match(siteUi, /site_desired_conflict/);
  assert.match(siteUi, /Desired changed elsewhere/);
  assert.match(siteUi, /Reset Draft to the latest Desired state before saving/);
  assert.match(siteUi, /isConflict/);
  assert.doesNotMatch(siteUi, /force.?save|overwrite.?anyway/i);
});
