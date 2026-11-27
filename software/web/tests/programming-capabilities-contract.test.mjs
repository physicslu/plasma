import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const capabilities = await readFile(new URL("../app/programming-capabilities.ts", import.meta.url), "utf8");
const production = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const factoryBackend = await readFile(new URL("../app/fleet/managed-factory-backend.ts", import.meta.url), "utf8");
const engineering = await readFile(new URL("../app/engineering/managed-programming-workspace.tsx", import.meta.url), "utf8");

test("Programming capability catalog keeps an explicit typed contract", () => {
  assert.match(capabilities, /synthetic_programming_image:\s*boolean/);
  assert.match(capabilities, /target_device_required:\s*boolean/);
  assert.match(capabilities, /ProgrammingCapabilityCatalog[\s\S]*programming_capabilities\?:\s*Partial<ProgrammingCapabilities>/);
  assert.doesNotMatch(capabilities, /LEGACY_SHARED_MOCK_CAPABILITIES/);
  assert.doesNotMatch(capabilities, /provider\s*===?\s*["']mock["']/);
});

test("the managed Factory catalog is fail-closed: no synthetic Image, Target IC required (U10)", () => {
  assert.match(factoryBackend, /export function managedFactoryCatalog\(topology: ManagedTopology\): ProgrammingCapabilityCatalog/);
  assert.match(factoryBackend, /programming_capabilities: \{ synthetic_programming_image: false, target_device_required: true \}/);
  // The standalone Browser capability resolver is retired with the standalone mode.
  assert.doesNotMatch(capabilities, /resolveProgrammingCapabilities/);
  for (const source of [production, engineering]) {
    assert.doesNotMatch(source, /resolveProgrammingCapabilities|syntheticProgrammingImageAvailable/);
    assert.doesNotMatch(source, /\.provider === "mock"/);
  }
});
