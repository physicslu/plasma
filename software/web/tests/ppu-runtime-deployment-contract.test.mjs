import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const engineering = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const deploymentPage = await readFile(new URL("../app/engineering/ppu-runtime-deployment-page.tsx", import.meta.url), "utf8");
const deployment = await readFile(new URL("../app/engineering/ppu-runtime-deployment.tsx", import.meta.url), "utf8");
const bootstrapApi = await readFile(new URL("../app/engineering/ppu-bootstrap-api.ts", import.meta.url), "utf8");
const bootstrapBff = await readFile(new URL("../app/api/manager/bootstrap-bff.ts", import.meta.url), "utf8");
const registryRoute = await readFile(new URL("../app/api/manager/registry/[...path]/route.ts", import.meta.url), "utf8");

test("PPU management exposes Runtime Deployment as an explicit sibling of configuration", () => {
  assert.match(engineering, /type PpuSiteSection = "configuration" \| "runtime"/);
  assert.match(engineering, /Runtime Deployment/);
  assert.match(engineering, /<PpuRuntimeDeploymentPage \/>/);
  assert.match(engineering, /selectPpuSiteSection\("runtime"\)/);
  assert.match(deploymentPage, /<PpuRuntimeDeployment entry=\{selectedEntry\} hasActiveExecution=\{busy\} \/>/);
});

test("Bootstrap browser transport is a dedicated exact allowlist, never generic Gateway relay", () => {
  assert.match(registryRoute, /relayManagerBootstrapRequest/);
  assert.match(registryRoute, /resource: "bootstrap"/);
  assert.match(bootstrapBff, /BOOTSTRAP_POST_ACTIONS/);
  assert.match(bootstrapBff, /\^pair\$/);
  assert.match(bootstrapBff, /\^uploads\$/);
  assert.match(bootstrapBff, /\^deployments\$/);
  assert.match(bootstrapBff, /uploads\/\$\{UPLOAD_ID\}\/chunks/);
  assert.match(bootstrapBff, /uploads\/\$\{UPLOAD_ID\}\/commit/);
  assert.doesNotMatch(bootstrapBff, /relayManagerPpuRequest|\/gateway/);
  assert.match(bootstrapBff, /bootstrap_route_not_allowed/);
});

test("Browser never owns the device credential after pairing", () => {
  assert.match(deployment, /type="password"/);
  assert.match(deployment, /setPairingToken\(""\)/);
  assert.match(deployment, /persisted there as a device-bound secret/);
  assert.match(bootstrapApi, /JSON\.stringify\(\{ token \}\)/);
  assert.doesNotMatch(bootstrapApi, /Authorization/);
  assert.doesNotMatch(bootstrapBff, /Authorization/);
});

test("Runtime kit upload uses bounded chunks and two integrity layers", () => {
  assert.match(deployment, /const CHUNK_BYTES = 1024 \* 1024/);
  assert.match(deployment, /parseSha256Sidecar/);
  assert.match(deployment, /sha256Hex\(buffer\)/);
  assert.match(deployment, /appendManagerPpuBootstrapChunk/);
  assert.match(deployment, /commitManagerPpuBootstrapUpload/);
  assert.match(deployment, /startManagerPpuBootstrapDeployment/);
  assert.match(bootstrapApi, /crypto\.subtle\.digest\("SHA-256"/);
  assert.match(bootstrapApi, /sidecar does not identify the selected kit/);
});

test("Console exposes proof boundaries instead of overstating release security or FPGA readiness", () => {
  assert.match(deployment, /SHA-256 proves integrity only/);
  assert.match(deployment, /publisher authenticity remains a production-hardening requirement/);
  assert.match(deployment, /FPGA Update/);
  assert.match(deployment, /Reserved \/ disabled/);
  assert.doesNotMatch(deployment, />Upgrade FPGA<|>Load Bitstream<|load_fpga|fpga_manager/);
});

test("Runtime deployment is blocked in UI when Sites are executing and target host remains Manager-owned", () => {
  assert.match(deploymentPage, /ACTIVE_SITE_STATES/);
  assert.match(deployment, /!hasActiveExecution/);
  assert.match(deployment, /Runtime deployment is blocked while any Site has an active Job/);
  assert.doesNotMatch(bootstrapApi, /gateway_host/);
});
