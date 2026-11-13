import assert from "node:assert/strict";
import test from "node:test";
import { buildIdentityForVite, identityFromProvenance } from "../build/build-identity.mjs";

const SHA = "abcdef1234567890abcdef1234567890abcdef12";
const OTHER = "1234567890abcdef1234567890abcdef12345678";
const VERSION = "0.2.1";

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

test("a new commit changes the build identity without changing Product Version", () => {
  const first = identityFromProvenance({ productVersion: VERSION, mode: "build", gitSha: SHA });
  const second = identityFromProvenance({ productVersion: VERSION, mode: "build", gitSha: OTHER });
  assert.equal(first.productVersion, second.productVersion);
  assert.notEqual(first.releaseId, second.releaseId);
});

test("a dirty source never claims an exact immutable build", () => {
  const result = identityFromProvenance({
    productVersion: VERSION, mode: "build", gitSha: SHA, dirty: true,
  });
  assert.equal(result.mode, "unknown");
  assert.equal(result.gitSha, null);
  assert.equal(result.releaseId, null);
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

  const both = buildIdentityForVite({
    mode: "build",
    env: { PLASMA_BUILD_GIT_SHA: SHA, RENDER_GIT_COMMIT: SHA },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(both.gitSha, SHA);

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

  const conflictingMetadata = buildIdentityForVite({
    mode: "build",
    env: { PLASMA_BUILD_GIT_SHA: SHA, RENDER_GIT_COMMIT: OTHER },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(conflictingMetadata.mode, "unknown");
  assert.equal(conflictingMetadata.gitSha, null);

  const emptyMetadata = buildIdentityForVite({
    mode: "build",
    env: { RENDER_GIT_COMMIT: "" },
    gitProbe: () => ({ sha: SHA, dirty: false }),
  });
  assert.equal(emptyMetadata.mode, "unknown");
});

test("dirty checkout cannot be made immutable by matching metadata", () => {
  const identity = buildIdentityForVite({
    mode: "build", env: { RENDER_GIT_COMMIT: SHA },
    gitProbe: () => ({ sha: SHA, dirty: true }),
  });
  assert.equal(identity.mode, "unknown");
  assert.equal(identity.dirty, true);
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

test("Render gate distinguishes source, metadata, and Git execution failures", () => {
  const probe = (overrides = {}) => () => ({
    sha: SHA, dirty: false, headState: "ok", statusState: "ok",
    trackedModified: 0, untracked: 0, ...overrides,
  });
  const resolve = (gitProbe, env = { RENDER_GIT_COMMIT: SHA }) =>
    buildIdentityForVite({ mode: "build", env, gitProbe, requireGitCheckout: true });

  assert.equal(resolve(probe()).mode, "build");
  assert.equal(resolve(probe({ sha: null }), {}).failureReason, "missing-or-invalid-git-head");
  assert.equal(resolve(probe(), { RENDER_GIT_COMMIT: "invalid" }).failureReason, "sha-metadata-invalid");
  assert.equal(resolve(probe(), { RENDER_GIT_COMMIT: OTHER }).failureReason, "sha-mismatch");
  assert.equal(resolve(probe(), { RENDER_GIT_COMMIT: SHA, PLASMA_BUILD_GIT_SHA: OTHER }).failureReason, "sha-mismatch");
  assert.equal(resolve(probe({ dirty: true, untracked: 1 })).failureReason, "dirty-source");
  assert.equal(resolve(probe({ dirty: true, trackedModified: 1 })).failureReason, "dirty-source");
  assert.equal(resolve(probe({ dirty: true, statusState: "timeout" })).failureReason, "git-status-timeout");
  assert.equal(resolve(probe({ dirty: true, statusState: "error" })).failureReason, "git-status-error");
  assert.equal(resolve(probe({ sha: null, headState: "timeout" })).failureReason, "git-head-timeout");
  assert.equal(resolve(probe({ sha: null, headState: "error" })).failureReason, "git-head-error");
});
