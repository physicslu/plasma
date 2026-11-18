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
  assert.match(api, /kind: "bundle", upload_id: uploadId, archive_sha256: archiveSha256/);
  assert.match(api, /execution_permitted !== false/);
  assert.match(api, /owner_authorized !== true/);
  assert.match(api, /OWNER_AUTHORIZED/);
  assert.match(api, /owner\?\.action !== "bundle\.admit"/);
  assert.match(api, /owner\?\.subject_sha256 !== archiveSha256/);
  // Retired per-Bundle device allowlist must not reappear in the Console.
  assert.doesNotMatch(api, /LOCAL_APPROVED|approved_bundle_sha256|source_authorized/);
  assert.doesNotMatch(ui, /LOCAL_APPROVED|approved_bundle_sha256|Master authorization/);
  assert.match(api, /package_admission_only/);
  assert.match(ui, /Verify & Admit Bundle \(No Install\)/);
  assert.match(ui, /admitManagerPpuBundle\(alias, created.upload.upload_id, digest\)/);
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
  assert.match(manager, /generic Bundle requires only kind, upload_id and archive_sha256/);
  assert.match(manager, /"kind": "bundle", "upload_id": upload_id/);
  assert.match(manager, /generic Bundle admission response is not owner-authorized and non-executing/);
  assert.match(manager, /owner_authorized/);
  assert.match(manager, /issue_bundle_operation/);
  assert.doesNotMatch(manager, /LOCAL_APPROVED|approved_bundle_sha256/);
  assert.match(server, /gate.try_begin_platform_launch\(alias\)/);
  assert.match(server, /_bootstrap_mutation_allowed\(alias\)/);
  assert.match(server, /coordinator.start_deployment\(alias, body\)/);
  assert.match(api, /export function startManagerPpuBootstrapDeployment/);
  assert.match(ui, /Update PPU Platform Release/);
  assert.doesNotMatch(api, /Bearer /);
  assert.doesNotMatch(ui, /Bearer /);
});

test("B3 Console control sends the exact admitted Bundle and explicit fpga_load choice through the BFF", async () => {
  const [api, ui, manager] = await Promise.all([read("api"), read("ui"), read("manager")]);
  assert.match(api, /export function installManagerPpuBundle/);
  assert.match(api, /admission_transaction_id: admitted.admissionTransactionId/);
  assert.match(api, /fpga_load: fpgaLoad/);
  assert.match(ui, /Install and Load FPGA/);
  assert.match(ui, /installManagerPpuBundle\(alias, admitted, fpgaLoad\)/);
  assert.match(ui, /deployment\?\.transaction_id === admitted.admissionTransactionId/);
  assert.match(ui, /runtime_site_readmission === "REQUIRED"/);
  assert.doesNotMatch(ui, /install_only/);
  assert.match(api, /mode: "activate",\n\s*fpga_load: fpgaLoad/);
  assert.doesNotMatch(api, /stage_only/);
  assert.match(manager, /admission_transaction_id, mode and fpga_load/);
  assert.match(manager, /ACTIVATE_FPGA_LOAD if body\["fpga_load"\] else\s+ACTIVATE if mode == "activate" else INSTALL/);
});

test("B3 Console body key set equals the Manager's required B3 key set", async () => {
  const [api, manager] = await Promise.all([read("api"), read("manager")]);
  const fn = api.slice(api.indexOf("export function installManagerPpuBundle"));
  const body = fn.slice(fn.indexOf("JSON.stringify({") + 16, fn.indexOf("}),"));
  const consoleKeys = [...body.matchAll(/(\w+):/g)].map(m => m[1]).sort();
  const required = manager.match(/if set\(body\) != \{([^}]*"admission_transaction_id"[^}]*)\}/);
  assert.ok(required, "Manager B3 required key set not found");
  const managerKeys = [...required[1].matchAll(/"(\w+)"/g)].map(m => m[1]).sort();
  assert.deepEqual(consoleKeys, managerKeys);
});
