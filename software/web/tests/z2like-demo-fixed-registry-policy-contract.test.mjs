import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const collection = new URL("../app/api/manager/registry/route.ts", import.meta.url);
const entry = new URL("../app/api/manager/registry/[...path]/route.ts", import.meta.url);
const renderStart = new URL("../../../scripts/render-control-station-start.sh", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("z2like Render registry remains fixed-target while allowing lifecycle maintenance", async () => {
  const [collectionSource, entrySource, startSource] = await Promise.all([
    source(collection),
    source(entry),
    source(renderStart),
  ]);

  assert.match(startSource, /PLASMA_MANAGER_REGISTRY_POLICY="fixed-lifecycle"/);
  assert.match(startSource, /registry_state_path/);
  assert.match(collectionSource, /fixed_registry_policy/);
  assert.match(collectionSource, /request\.method === "POST"/);
  assert.match(entrySource, /request\.method === "DELETE"/);
  assert.match(entrySource, /alias !== fixedAlias/);
  assert.match(entrySource, /lifecycle !== "disabled" && lifecycle !== "commissioned"/);
  assert.match(entrySource, /Object\.keys\(payload\)\.length !== 1/);
});
