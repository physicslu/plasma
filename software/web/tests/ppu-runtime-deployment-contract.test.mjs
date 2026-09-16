import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);
const files = {
  page: new URL("engineering/page.tsx", root),
  deploymentPage: new URL("engineering/ppu-runtime-deployment-page.tsx", root),
  deployment: new URL("engineering/ppu-runtime-deployment.tsx", root),
  api: new URL("engineering/ppu-bootstrap-api.ts", root),
  bff: new URL("api/manager/bootstrap-bff.ts", root),
  route: new URL("api/manager/registry/[...path]/route.ts", root),
  managerServer: new URL("../../python/plasma_manager/server.py", import.meta.url),
  bootstrapServer: new URL("../../python/plasma_manager/bootstrap_server.py", import.meta.url),
};

async function source(url) {
  return readFile(url, "utf8");
}

test("EMode exposes PPU Overview, Platform, Registration, and Sites as separate functional surfaces", async () => {
  const page = await source(files.page);
  assert.match(page, /type PpuSection = "overview" \| "platform" \| "registration" \| "sites"/);
  assert.match(page, /<PpuOverviewPage onNavigate=\{selectPpuSection\} \/>/);
  assert.match(page, /<PpuRuntimeDeploymentPage \/>/);
  assert.match(page, /<PpuRegistrationPage \/>/);
  assert.match(page, /<PpuSitesPage \/>/);
  for (const label of ["Overview", "Platform", "Registration", "Sites"]) {
    assert.match(page, new RegExp(`engineeringNavLabel">${label}<`));
  }
  assert.match(page, /settingsSubgroupLabels/);
  assert.match(page, /navGroupLabels/);
});

test("Platform surface is explicitly independent from programming Registration", async () => {
  const platform = await source(files.deploymentPage);
  assert.match(platform, /PPU Platform Release Workspace/);
  assert.match(platform, /independently of programming Registration/);
  assert.match(platform, /Operational Registration is a separate programming-management admission state/);
  assert.doesNotMatch(platform, /PPU \/ Site Configuration/);
});

test("Platform Release update preserves lifecycle, idle, recovery, and artifact-integrity gates", async () => {
  const deployment = await source(files.deployment);
  assert.match(deployment, /entry\.lifecycle === "pending"/);
  assert.match(deployment, /entry\.lifecycle === "disabled" && hasTrustedIdleObservation/);
  assert.match(deployment, /entry\.lifecycle === "commissioned"/);
  assert.match(deployment, /recovery_required/);
  assert.match(deployment, /hasActiveExecution/);
  assert.match(deployment, /parseSha256Sidecar/);
  assert.match(deployment, /sha256Hex/);
  assert.match(deployment, /Update PPU Platform Release/);
  assert.match(deployment, /Bootstrap remains independently versioned and is not silently rewritten by this path/);
  assert.match(deployment, /Programming Logic, including FPGA bitstreams and ICPN-selected Python logic, is a separate lifecycle/);
  assert.doesNotMatch(deployment, /gateway_host/);
});

test("Platform maintenance pairing is separate from programming Registration", async () => {
  const deployment = await source(files.deployment);
  assert.match(deployment, /Platform Maintenance Pairing Token/);
  assert.match(deployment, /Authorize Platform Maintenance/);
  assert.match(deployment, /does not register the PPU for managed programming operations/);
  assert.match(deployment, /pairManagerPpuBootstrap/);
});

test("Platform PS Loop Test reuses Runtime loopback without requiring programming Registration", async () => {
  const [deployment, api, bff, bootstrapServer, managerServer] = await Promise.all([
    source(files.deployment),
    source(files.api),
    source(files.bff),
    source(files.bootstrapServer),
    source(files.managerServer),
  ]);
  assert.match(deployment, /Run PS Loop Test/);
  assert.match(deployment, /runManagerPpuPlatformPsLoopback/);
  assert.match(deployment, /runtime\?\.state === "runtime_active"/);
  assert.match(deployment, /Programming Registration is not required/);
  assert.match(api, /\/ps-loopback/);
  assert.match(api, /endpoint: "ps"/);
  assert.match(bff, /\^ps-loopback\$/);
  assert.match(bootstrapServer, /action == "ps-loopback"/);
  assert.match(bootstrapServer, /context": "platform"/);
  assert.match(bootstrapServer, /client\.ps_loopback\(body/);
  assert.match(managerServer, /self\.command == "POST" and self\._registry_lifecycle\(alias\) != REGISTRY_LIFECYCLE_COMMISSIONED/);
});

test("Browser Platform path remains bounded, maintenance-authorized, and Manager-only", async () => {
  const [api, bff, route] = await Promise.all([source(files.api), source(files.bff), source(files.route)]);
  assert.match(api, /appendManagerPpuBootstrapChunk|uploads\/\$\{encodeURIComponent\(uploadId\)\}\/chunks/);
  assert.match(bff, /MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES = 2 \* 1024 \* 1024/);
  assert.match(bff, /managerApiBase\(\)/);
  assert.match(bff, /bootstrapActionAllowed/);
  assert.match(bff, /hasMaintenanceCapability/);
  assert.doesNotMatch(bff, /Authorization/);
  assert.match(route, /relayManagerBootstrapRequest/);
  assert.match(route, /resource: "bootstrap"/);
});
