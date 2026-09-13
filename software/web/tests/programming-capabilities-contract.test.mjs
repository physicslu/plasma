import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const capabilities = await readFile(new URL("../app/programming-capabilities.ts", import.meta.url), "utf8");
const production = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const engineering = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("Programming capability resolver uses an explicit fail-closed catalog contract", () => {
  assert.match(capabilities, /synthetic_programming_image:\s*boolean/);
  assert.match(capabilities, /target_device_required:\s*boolean/);
  assert.match(capabilities, /ProgrammingCapabilityCatalog[\s\S]*programming_capabilities\?:\s*Partial<ProgrammingCapabilities>/);
  assert.match(capabilities, /FAIL_CLOSED_CAPABILITIES[\s\S]*synthetic_programming_image:\s*false[\s\S]*target_device_required:\s*true/);
  assert.match(capabilities, /typeof advertised\.synthetic_programming_image !== "boolean"/);
  assert.match(capabilities, /typeof advertised\.target_device_required !== "boolean"/);
  assert.doesNotMatch(capabilities, /LEGACY_SHARED_MOCK_CAPABILITIES/);
  assert.doesNotMatch(capabilities, /provider\s*===?\s*["']mock["']/);
});

test("PMode and EMode consume the shared capability resolver instead of provider-name policy", () => {
  assert.match(production, /resolveProgrammingCapabilities\(catalog\)/);
  assert.match(engineering, /resolveProgrammingCapabilities\(catalog\)/);
  assert.doesNotMatch(production, /\.provider === "mock"/);
  assert.doesNotMatch(engineering, /\.provider === "mock"/);
  assert.match(production, /syntheticProgrammingImageAvailable/);
  assert.match(engineering, /syntheticProgrammingImageAvailable/);
});
