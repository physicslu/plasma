import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const files = {
  api: "../app/engineering/ppu-bootstrap-api.ts",
  ui: "../app/engineering/ppu-runtime-deployment.tsx",
  bff: "../app/api/manager/bootstrap-bff.ts",
  route: "../app/api/manager/registry/[...path]/route.ts",
  manager: "../../python/plasma_manager/bootstrap.py",
  server: "../../python/plasma_manager/bootstrap_server.py",
};
const read = async name => readFile(new URL(files[name], import.meta.url), "utf8");

test("PR3 Console Bundle uses the existing BFF/Manager Bootstrap API, never a new PPU token", async () => {
  const [api, ui, bff, route] = await Promise.all([
    read("api"), read("ui"), read("bff"), read("route"),
  ]);
  assert.match(api, /export function admitManagerPpuBundle/);
  assert.match(api, /kind: "bundle", upload_id: uploadId/);
  assert.match(api, /execution_permitted !== false/);
  assert.match(api, /package_admission_only/);
  assert.match(ui, /Verify & Admit Bundle \(No Install\)/);
  assert.match(ui, /admitManagerPpuBundle\(alias, created.upload.upload_id\)/);
  assert.match(ui, /commitManagerPpuBootstrapUpload/);
  assert.match(ui, /Admitting/);
  assert.match(bff, /hasMaintenanceCapability/);
  assert.match(bff, /maintenanceMutationOriginAllowed/);
  assert.match(bff, /MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES/);
  assert.match(bff, /managerApiBase\(\)/);
  assert.doesNotMatch(bff, /Authorization/);
  assert.match(route, /relayManagerBootstrapRequest/);
  assert.doesNotMatch(ui, /fetch\("http:\/\/192\.168\./);
});

test("PR3 preserves single Manager deployment operation gate and PPU internal ownership", async () => {
  const [manager, server, api, ui] = await Promise.all([
    read("manager"), read("server"), read("api"), read("ui"),
  ]);
  assert.match(manager, /if body.get\("kind"\) == "bundle":/);
  assert.match(manager, /generic Bundle requires only kind and upload_id/);
  assert.match(manager, /"kind": "bundle", "upload_id": upload_id/);
  assert.match(manager, /generic Bundle admission response is not non-executing/);
  assert.match(server, /gate.try_begin_platform_launch\(alias\)/);
  assert.match(server, /_bootstrap_mutation_allowed\(alias\)/);
  assert.match(server, /coordinator.start_deployment\(alias, body\)/);
  assert.match(api, /export function startManagerPpuBootstrapDeployment/);
  assert.match(ui, /Update PPU Platform Release/);
  assert.doesNotMatch(api, /Bearer /);
  assert.doesNotMatch(ui, /Bearer /);
});
