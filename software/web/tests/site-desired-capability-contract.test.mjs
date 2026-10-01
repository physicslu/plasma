import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const desiredUi = await readFile(
  new URL("../app/engineering/ppu-site-desired-configuration.tsx", import.meta.url),
  "utf8",
);
const capability = await readFile(
  new URL("../app/engineering/ppu-runtime-activation-capability.ts", import.meta.url),
  "utf8",
);

test("Site Desired reuses the exact Site-settings missing-route classifier", () => {
  assert.match(desiredUi, /isMissingSiteSettingsCapabilityRoute/);
  assert.match(capability, /export function isMissingSiteSettingsCapabilityRoute/);
  assert.match(capability, /error instanceof ManagerApiError/);
  assert.match(capability, /error\.status === 404/);
  assert.match(capability, /error\.code === null/);
  assert.match(capability, /error\.message === "not found"/);

  // A coded Manager 404 such as ppu_not_found must not become capability
  // unsupported; the existing core UI remains responsible for real faults.
  assert.match(desiredUi, /isMissingSiteSettingsCapabilityRoute\(error\) \? "unsupported" : "supported"/);
});

test("Site Desired collapses unsupported configuration capability into one non-fault summary", () => {
  assert.match(desiredUi, /SiteDesiredCapabilityState = "checking" \| "supported" \| "unsupported"/);
  assert.match(desiredUi, /ppuCapabilitySummaryCard/);
  assert.match(desiredUi, /Programming Configuration/);
  assert.match(desiredUi, /Site Desired Configuration/);
  assert.match(desiredUi, /Runtime Activation/);
  assert.match(desiredUi, /Not Supported/);
  assert.match(desiredUi, /This is a capability boundary, not a runtime fault\./);
  assert.match(desiredUi, /Observed Site topology is independent from configuration and Runtime-activation capability/);
  assert.match(desiredUi, /siteDesiredCapability === "supported"/);
  assert.match(desiredUi, /<PpuSiteDesiredConfigurationCore \{\.\.\.props\} \/>/);
  assert.match(desiredUi, /<PpuRuntimeActivation \{\.\.\.props\} \/>/);
  assert.doesNotMatch(desiredUi, /setError\([^\n]*Not supported by this PPU profile/);
});
