// Identifies the exact Console source built into its immutable UI bundle.
// Product version is not a per-commit counter. Never infer a SHA from a
// running PPU, a Manager API response, or the Browser's current URL.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const MANIFEST = JSON.parse(readFileSync(new URL("../../../release/product.json", import.meta.url), "utf8"));
const SHA40 = /^[a-f0-9]{40}$/i;

function cleanSha(value) {
  return typeof value === "string" && SHA40.test(value.trim())
    ? value.trim().toLowerCase() : null;
}

function gitCommand(args) {
  try {
    return { state: "ok", output: execFileSync("git", args, {
      cwd: ROOT, encoding: "utf8", timeout: 30000, stdio: ["ignore", "pipe", "ignore"],
    }).trim() };
  } catch (error) {
    return { state: error?.code === "ETIMEDOUT" ? "timeout" : "error", output: null };
  }
}

export function inspectSourceGit() {
  const head = gitCommand(["rev-parse", "--verify", "HEAD"]);
  const status = gitCommand(["status", "--porcelain", "--untracked-files=normal"]);
  const sha = cleanSha(head.output);
  const entries = status.output ? status.output.split("\n") : [];
  const untracked = entries.filter(entry => entry.startsWith("??")).length;
  const trackedModified = entries.length - untracked;
  // A packaged source tree may have no .git; trust explicit pinned build
  // metadata there, but never infer an unpinned SHA.
  return {
    sha, dirty: sha !== null && (status.state !== "ok" || entries.length > 0),
    headState: head.state === "ok" && !sha ? "invalid" : head.state,
    statusState: status.state, trackedModified, untracked,
  };
}

export function identityFromProvenance({
  productVersion, mode, gitSha, dirty = false, source = "unknown",
}) {
  const sha = cleanSha(gitSha);
  if (mode === "dev") {
    return {
      productVersion, mode: "dev", gitSha: sha, shortSha: sha?.slice(0, 12) ?? null,
      releaseId: null, source, dirty: Boolean(dirty),
    };
  }
  if (!sha || dirty) {
    return {
      productVersion, mode: "unknown", gitSha: null, shortSha: null,
      releaseId: null, source: "unknown", dirty: Boolean(dirty),
    };
  }
  return {
    productVersion, mode: "build", gitSha: sha, shortSha: sha.slice(0, 12),
    releaseId: `${productVersion}-${sha.slice(0, 12)}`, source, dirty: false,
  };
}

export function buildIdentityForVite({
  mode, env = process.env, gitProbe = inspectSourceGit, requireGitCheckout = false,
}) {
  const version = MANIFEST.product_version;
  const git = gitProbe();
  const supplied = [env.PLASMA_BUILD_GIT_SHA, env.RENDER_GIT_COMMIT]
    .filter(value => value !== undefined);
  const validated = supplied.map(cleanSha);
  const pinned = validated[0] ?? null;
  const metadataInvalid = supplied.length > 0 && validated.some(sha => !sha);
  const metadataConflict = !metadataInvalid && validated.some(sha => sha !== pinned);
  const validPinned = supplied.length > 0 && !metadataInvalid && !metadataConflict;
  // A provided (but invalid or mismatching) source SHA must never fall back
  // to a plausible-looking git HEAD and claim an immutable deployment.
  const mismatch = metadataConflict || (validPinned && git.sha && git.sha !== pinned);
  const checkoutFailure = requireGitCheckout && (!git.sha || git.statusState !== "ok");
  const conflict = metadataInvalid || mismatch || checkoutFailure;
  const source = supplied.length > 0 ? "build-metadata" : "git-checkout";
  const identity = identityFromProvenance({
    productVersion: version,
    mode: mode === "dev" ? "dev" : "build",
    gitSha: conflict ? null : (pinned || git.sha),
    dirty: Boolean(git.dirty || conflict),
    source,
  });
  if (identity.mode !== "unknown") return identity;
  const failureReason = git.headState === "timeout" ? "git-head-timeout"
    : git.headState === "error" ? "git-head-error"
    : git.statusState === "timeout" ? "git-status-timeout"
    : git.statusState === "error" && git.sha ? "git-status-error"
    : metadataInvalid ? "sha-metadata-invalid"
    : mismatch ? "sha-mismatch"
    : git.trackedModified > 0 || git.untracked > 0 || git.dirty ? "dirty-source"
    : "missing-or-invalid-git-head";
  return { ...identity, failureReason };
}
