import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);
const files = {
  page: new URL("engineering/page.tsx", root),
  deployment: new URL("engineering/ppu-runtime-deployment.tsx", root),
  api: new URL("engineering/ppu-bootstrap-api.ts", root),
  bff: new URL("api/manager/bootstrap-bff.ts", root),
  route: new URL("api/manager/registry/[...path]/route.ts", root),
};

async function source(url) {
  return readFile(url, "utf8");
}

test("EMode exposes Runtime Deployment beneath PPU Sites without replacing current IA", async () => {
  const page = await source(files.page);
  assert.match(page, /type PpuSiteSection = "configuration" \| "runtime"/);
  assert.match(page, /<PpuRuntimeDeploymentPage \/>/);
  assert.match(page, /Runtime 部署/);
  assert.match(page, /settingsSubgroupLabels/);
  assert.match(page, /navGroupLabels/);
});

test("Console deployment is lifecycle-gated and does not own Gateway host routing", async () => {
  const deployment = await source(files.deployment);
  assert.match(deployment, /entry\.lifecycle === "pending"/);
  assert.match(deployment, /entry\.lifecycle === "disabled" && hasTrustedIdleObservation/);
  assert.match(deployment, /entry\.lifecycle === "commissioned"/);
  assert.match(deployment, /recovery_required/);
  assert.match(deployment, /hasActiveExecution/);
  assert.doesNotMatch(deployment, /gateway_host/);
  assert.match(deployment, /SHA-256 does not prove publisher authenticity/);
  assert.match(deployment, /FPGA bitstream loading remains disabled/);
});

test("Browser upload path is bounded and Manager-only", async () => {
  const [api, bff, route] = await Promise.all([source(files.api), source(files.bff), source(files.route)]);
  assert.match(api, /CHUNK|appendManagerPpuBootstrapChunk|uploads\/\$\{encodeURIComponent\(uploadId\)\}\/chunks/);
  assert.match(bff, /MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES = 2 \* 1024 \* 1024/);
  assert.match(bff, /managerApiBase\(\)/);
  assert.match(bff, /bootstrapActionAllowed/);
  assert.doesNotMatch(bff, /Authorization/);
  assert.match(route, /relayManagerBootstrapRequest/);
  assert.match(route, /resource: "bootstrap"/);
});
