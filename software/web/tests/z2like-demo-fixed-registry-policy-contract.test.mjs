import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const collection = new URL("../app/api/manager/registry/route.ts", import.meta.url);
const entry = new URL("../app/api/manager/registry/[...path]/route.ts", import.meta.url);
const capability = new URL("../app/api/manager/maintenance-capability.mjs", import.meta.url);
const renderStart = new URL("../../../scripts/render-control-station-start.sh", import.meta.url);
const renderBlueprint = new URL("../../../render.yaml", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("z2like Render registry remains fixed-target with pairing-gated lifecycle maintenance", async () => {
  const [collectionSource, entrySource, capabilitySource, startSource, blueprintSource] = await Promise.all([
    source(collection),
    source(entry),
    source(capability),
    source(renderStart),
    source(renderBlueprint),
  ]);

  assert.match(startSource, /PLASMA_MANAGER_REGISTRY_POLICY="fixed-lifecycle"/);
  assert.match(startSource, /registry_state_path/);
  assert.match(collectionSource, /fixed_registry_policy/);
  assert.match(collectionSource, /request\.method === "POST"/);
  assert.match(entrySource, /request\.method === "DELETE"/);
  assert.match(entrySource, /alias !== fixedAlias/);
  assert.match(entrySource, /lifecycle !== "disabled" && lifecycle !== "commissioned"/);
  assert.match(entrySource, /Object\.keys\(payload\)\.length !== 1/);
  assert.match(entrySource, /hasMaintenanceCapability\(request, alias\)/);
  assert.match(entrySource, /maintenanceCapabilityRequired\(\)/);
  assert.match(capabilitySource, /HttpOnly; Secure; SameSite=Strict/);
  assert.match(capabilitySource, /createHmac\("sha256"/);
  assert.match(capabilitySource, /CAPABILITY_TTL_SECONDS = 15 \* 60/);
  assert.match(blueprintSource, /PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET/);
  assert.match(blueprintSource, /generateValue: true/);
});
