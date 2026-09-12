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

test("Site Desired renders unsupported capability as a non-fault state", () => {
  assert.match(desiredUi, /SiteDesiredCapabilityState = "checking" \| "supported" \| "unsupported"/);
  assert.match(desiredUi, /Not Supported/);
  assert.match(desiredUi, /Not supported by this PPU profile\. This is a capability boundary, not a runtime fault\./);
  assert.match(desiredUi, /This PPU profile does not expose Site Desired Configuration\./);
  assert.match(desiredUi, /siteDesiredCapability === "supported"/);
  assert.match(desiredUi, /<PpuSiteDesiredConfigurationCore \{\.\.\.props\} \/>/);
  assert.doesNotMatch(desiredUi, /setError\([^\n]*Not supported by this PPU profile/);
});
