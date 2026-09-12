import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const capabilities = await readFile(new URL("../app/programming-capabilities.ts", import.meta.url), "utf8");
const production = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const engineering = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("Programming capability resolver separates synthetic Image support from Target IC admission", () => {
  assert.match(capabilities, /synthetic_programming_image:\s*boolean/);
  assert.match(capabilities, /target_device_required:\s*boolean/);
  assert.match(capabilities, /FAIL_CLOSED_CAPABILITIES[\s\S]*synthetic_programming_image:\s*false[\s\S]*target_device_required:\s*true/);
  assert.match(capabilities, /LEGACY_SHARED_MOCK_CAPABILITIES[\s\S]*synthetic_programming_image:\s*true[\s\S]*target_device_required:\s*false/);
  assert.match(capabilities, /catalog\?\.provider === "mock"/);
});

test("PMode and EMode consume the shared capability resolver instead of provider-name policy", () => {
  assert.match(production, /resolveProgrammingCapabilities\(catalog\)/);
  assert.match(engineering, /resolveProgrammingCapabilities\(catalog\)/);
  assert.doesNotMatch(production, /\.provider === "mock"/);
  assert.doesNotMatch(engineering, /\.provider === "mock"/);
  assert.match(production, /syntheticProgrammingImageAvailable/);
  assert.match(engineering, /syntheticProgrammingImageAvailable/);
});
