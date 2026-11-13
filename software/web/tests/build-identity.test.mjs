import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { buildIdentityForVite, identityFromProvenance } from "../build/build-identity.mjs";

const SHA = "abcdef1234567890abcdef1234567890abcdef12";
const OTHER = "1234567890abcdef1234567890abcdef12345678";
const VERSION = "0.2.1";

test("Console header renders Build followed by the short SHA", () => {
  const label = readFileSync(new URL("../app/build-identity.ts", import.meta.url), "utf8");
  const nav = readFileSync(new URL("../app/global-nav.tsx", import.meta.url), "utf8");
  assert.ok(label.includes(`Build ${identity.shortSha}`));
  assert.ok(nav.includes("consoleBuildLabel(PLASMA_BUILD_IDENTITY)"));
});

test("a clean source build binds the full git SHA and 12-digit Release ID", () => {
  const identity = identityFromProvenance({
    productVersion: VERSION, mode: "build", gitSha: SHA, dirty: false, source: "git-checkout",
  });
  assert.equal(identity.mode, "build");
  assert.equal(identity.gitSha, SHA);
  assert.equal(identity.shortSha, "abcdef123456");
  assert.equal(identity.releaseId, "0.2.1-abcdef123456");
  assert.equal(identity.productVersion, VERSION);
});

test("Build SHA remains available when Render checkout is dirty", () => {
  const result = buildIdentityForVite({
    mode: "build", env: { RENDER_GIT_COMMIT: SHA },
    gitProbe: () => ({ sha: SHA, dirty: true }),
  });
  assert.equal(result.productVersion, "0.2.1");
  assert.equal(result.mode, "build");
  assert.equal(result.shortSha, "abcdef123456");
  assert.equal(result.gitSha, SHA);
  assert.equal(result.dirty, true);
});

test("development has no release claim even when git HEAD is valid", () => {
  const result = identityFromProvenance({
    productVersion: VERSION, mode: "dev", gitSha: SHA, dirty: true,
  });
  assert.equal(result.mode, "dev");
  assert.equal(result.dirty, true);
  assert.equal(result.releaseId, null);
});

test("a pinned Render or package SHA is checked against the checkout", () => {
  const clean = buildIdentityForVite({
    mode: "build",
    env: { RENDER_GIT_COMMIT: SHA },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(clean.releaseId, "0.2.1-abcdef123456");
  assert.equal(clean.source, "build-metadata");

  const mismatched = buildIdentityForVite({
    mode: "build",
    env: { PLASMA_BUILD_GIT_SHA: OTHER },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(mismatched.mode, "unknown");
  assert.equal(mismatched.gitSha, null);

  const malformed = buildIdentityForVite({
    mode: "build",
    env: { RENDER_GIT_COMMIT: "xyz" },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(malformed.mode, "unknown");
});

test("an absent checkout without a pinned source is explicitly UNKNOWN", () => {
  const identity = buildIdentityForVite({
    mode: "build",
    env: {},
    gitProbe: () => ({ sha: null, dirty: false }),
  });
  assert.equal(identity.mode, "unknown");
  assert.equal(identity.releaseId, null);
});

test("explicit immutable source metadata works when packaged outside git", () => {
  const identity = buildIdentityForVite({
    mode: "build",
    env: { PLASMA_BUILD_GIT_SHA: SHA },
    gitProbe: () => ({ sha: null, dirty: false }),
  });
  assert.equal(identity.releaseId, "0.2.1-abcdef123456");
});
