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
  assert.match(platform, /PPU Platform Firmware Workspace/);
  assert.match(platform, /independently of programming Registration/);
  assert.match(platform, /entry\.lifecycle === "pending"|PpuRuntimeDeployment/);
  assert.match(platform, /Operational Registration is a separate programming-management admission state/);
  assert.doesNotMatch(platform, /PPU \/ Site Configuration/);
});

test("Platform Firmware update preserves lifecycle, idle, recovery, and artifact-integrity gates", async () => {
  const deployment = await source(files.deployment);
  assert.match(deployment, /entry\.lifecycle === "pending"/);
  assert.match(deployment, /entry\.lifecycle === "disabled" && hasTrustedIdleObservation/);
  assert.match(deployment, /entry\.lifecycle === "commissioned"/);
  assert.match(deployment, /recovery_required/);
  assert.match(deployment, /hasActiveExecution/);
  assert.match(deployment, /parseSha256Sidecar/);
  assert.match(deployment, /sha256Hex/);
  assert.match(deployment, /Update PPU Platform Firmware/);
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

test("Browser upload path remains bounded and Manager-only", async () => {
  const [api, bff, route] = await Promise.all([source(files.api), source(files.bff), source(files.route)]);
  assert.match(api, /appendManagerPpuBootstrapChunk|uploads\/\$\{encodeURIComponent\(uploadId\)\}\/chunks/);
  assert.match(bff, /MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES = 2 \* 1024 \* 1024/);
  assert.match(bff, /managerApiBase\(\)/);
  assert.match(bff, /bootstrapActionAllowed/);
  assert.doesNotMatch(bff, /Authorization/);
  assert.match(route, /relayManagerBootstrapRequest/);
  assert.match(route, /resource: "bootstrap"/);
});
