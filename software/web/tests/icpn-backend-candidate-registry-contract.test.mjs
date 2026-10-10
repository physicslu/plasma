import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("IC Selector displays ST candidate evidence without turning it into an executable mapping", async () => {
  const selector = await source("../app/devices/ic-selector.tsx");
  const api = await source("../app/device-catalog-api.ts");
  assert.match(api, /backend_candidate\?:\s*BackendCandidateEvidence\s*\|\s*null/);
  assert.match(api, /status:\s*"research_only"/);
  assert.match(api, /executable:\s*false/);
  assert.match(api, /production_binding_authorized:\s*false/);
  assert.match(api, /hardware_runtime_ready:\s*false/);
  assert.match(selector, /device\.backend\.mapping_status/);
  assert.match(selector, /device\.backend_candidate\?\.status\s*===\s*"research_only"/);
  assert.match(selector, /selected\.backend_candidate\.expected_device_id/);
  assert.match(selector, /selected\.backend_candidate\.loader_source_path/);
  assert.match(selector, /selected\.backend_candidate\.source_commit/);
  assert.match(selector, /selected\.backend_candidate\.dfp_exact_variant_status/);
  assert.match(selector, /禁止燒錄/);
  assert.match(selector, /尚不可燒錄/);
  assert.match(selector, /無法視為已支援燒錄/);
  assert.doesNotMatch(selector, /device\.backend_candidate\.executable\s*\?\s*onSelect/);
});

test("Candidate data never becomes a device-selector Job payload", async () => {
  const picker = await source("../app/devices/ic-picker-field.tsx");
  const selector = await source("../app/devices/ic-selector.tsx");
  assert.match(picker, /Search admitted ICPN/);
  assert.match(selector, /onSelect\?\.\(device\)/);
  assert.doesNotMatch(picker, /backend_candidate/);
});
