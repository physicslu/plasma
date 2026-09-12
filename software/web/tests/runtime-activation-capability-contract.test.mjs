import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const capability = await readFile(
  new URL("../app/engineering/ppu-runtime-activation-capability.ts", import.meta.url),
  "utf8",
);
const activationUi = await readFile(
  new URL("../app/engineering/ppu-runtime-activation.tsx", import.meta.url),
  "utf8",
);

test("runtime activation capability only normalizes the narrow legacy missing-route 404", () => {
  assert.match(capability, /error instanceof ManagerApiError/);
  assert.match(capability, /error\.status === 404/);
  assert.match(capability, /error\.code === null/);
  assert.match(capability, /error\.message === "not found"/);
  assert.match(capability, /reason: "site-settings-route-unavailable"/);
  assert.match(capability, /reason: "runtime-apply-disabled"/);

  // A Manager-owned 404 such as ppu_not_found carries a code and therefore
  // cannot be silently reclassified as an unsupported PPU capability.
  assert.doesNotMatch(capability, /error\.status === 404\s*\)\s*return/);
});

test("runtime activation UI renders unsupported capability as a non-fault state", () => {
  assert.match(activationUi, /getRuntimeActivationCapability/);
  assert.match(activationUi, /capabilityUnsupported/);
  assert.match(activationUi, /Not supported by this PPU profile\./);
  assert.match(activationUi, /This is a capability boundary, not a runtime fault\./);
  assert.match(activationUi, /Not Supported/);
  assert.match(activationUi, /disabled=\{Boolean\(blockReason\) \|\| activating\}/);
  assert.doesNotMatch(activationUi, /setError\([^\n]*Not supported by this PPU profile/);
});
