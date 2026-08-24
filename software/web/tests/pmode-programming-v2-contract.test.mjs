import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("PMode Programming v2 exposes the approved operator workflow", async () => {
  const page = await source("../app/fleet/programming/production-programming-page.tsx");

  assert.match(page, /SINGLE PPU PROGRAMMING/);
  assert.match(page, /SYSTEM SETUP &amp; TARGETING/);
  assert.match(page, /PROGRAMMING JOB/);
  assert.match(page, /1\. Target IC/);
  assert.match(page, /2\. Programming Image/);
  assert.match(page, /3\. Operations/);
  assert.match(page, /4\. Batch Policy/);
  assert.match(page, /START PROGRAMMING/);
  assert.match(page, /LIVE SITE STATUS/);
  assert.match(page, /RECENT EVENTS/);
});

test("PMode Site operations keep E P V R directly visible", async () => {
  const page = await source("../app/fleet/programming/production-programming-page.tsx");
  const css = await source("../app/fleet/programming/production-programming.css");

  assert.match(page, /OPERATIONS \(E\/P\/V\/R\)/);
  assert.match(page, /siteOperationButtons/);
  assert.match(page, /operationOrder\.map\(operation =>/);
  assert.match(css, /\.siteOperationButtons\s*\{/);
  assert.doesNotMatch(page, /ACTIONS/);
});

test("Stop Policy is a compact PMode control rather than a stretched field", async () => {
  const css = await source("../app/fleet/programming/production-programming.css");

  assert.match(css, /\.repeatField input\s*\{[^}]*width:\s*72px/s);
  assert.match(css, /\.stopPolicyField select\s*\{[^}]*width:\s*118px/s);
  assert.doesNotMatch(css, /\.stopPolicyField select\s*\{[^}]*flex:\s*1/s);
});

test("PMode programming draft binds target IC, Image, EPVR and Batch policy before adapting to server Batch", async () => {
  const domain = await source("../app/production-programming-domain.ts");
  const api = await source("../app/server-batch-api.ts");

  assert.match(domain, /ProductionProgrammingJobDraft/);
  assert.match(domain, /targetDevice:\s*DeviceSearchResult \| null/);
  assert.match(domain, /programmingImage:\s*File \| null/);
  assert.match(domain, /operations:\s*Operation\[\]/);
  assert.match(domain, /repeatCount:\s*number/);
  assert.match(domain, /stopPolicy:\s*ProductionStopPolicy/);
  assert.match(domain, /DEFAULT_PRODUCTION_SITE_RETRY_LIMIT = 3/);
  assert.match(domain, /buildServerBatchOptions/);
  assert.match(domain, /targetDevice:\s*draft\.targetDevice/);
  assert.match(domain, /failed_site_stop_threshold/);
  assert.match(api, /target_device:\s*BatchTargetDeviceSnapshot \| null/);
  assert.match(api, /target_device:\s*options\.targetDevice/);
});

test("PMode advertises only the currently implemented binary Programming Image format", async () => {
  const page = await source("../app/fleet/programming/production-programming-page.tsx");

  assert.match(page, /accept="\.bin"/);
  assert.match(page, /Select programming image \(\.bin\)/);
  assert.match(page, /supports binary Programming Image \(\.bin\) only/);
  assert.doesNotMatch(page, /accept="[^"]*\.hex/);
});

test("compact IC picker uses the shared device search service", async () => {
  const picker = await source("../app/devices/ic-picker-field.tsx");

  assert.match(picker, /searchDevices/);
  assert.match(picker, /DeviceSearchResult/);
  assert.match(picker, /Target IC search results/);
  assert.match(picker, /Exact ICPN/);
});
