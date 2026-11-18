// Displays the source commit SHA baked into the Console UI bundle.
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
    return execFileSync("git", args, {
      cwd: ROOT, encoding: "utf8", timeout: 3000, stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

export function inspectSourceGit() {
  const sha = cleanSha(gitCommand(["rev-parse", "--verify", "HEAD"]));
  const status = gitCommand(["status", "--porcelain", "--untracked-files=normal"]);
  // A packaged source tree may have no .git; trust explicit pinned build
  // metadata there, but never infer an unpinned SHA.
  return { sha, dirty: sha !== null && (status === null || status.length > 0) };
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
  if (!sha) {
    return {
      productVersion, mode: "unknown", gitSha: null, shortSha: null,
      releaseId: null, source: "unknown", dirty: Boolean(dirty),
    };
  }
  return {
    productVersion, mode: "build", gitSha: sha, shortSha: sha.slice(0, 12),
    releaseId: `${productVersion}-${sha.slice(0, 12)}`, source, dirty: Boolean(dirty),
  };
}

export function buildIdentityForVite({
  mode, env = process.env, gitProbe = inspectSourceGit,
}) {
  const version = MANIFEST.product_version;
  const git = gitProbe();
  const pinned = env.PLASMA_BUILD_GIT_SHA?.trim() || env.RENDER_GIT_COMMIT?.trim() || null;
  const validPinned = pinned ? cleanSha(pinned) : null;
  // A provided (but invalid or mismatching) source SHA must never fall back
  // to a plausible-looking git HEAD and claim an immutable deployment.
  const conflict = pinned && (!validPinned || (git.sha && git.sha !== validPinned));
  const source = pinned ? "build-metadata" : "git-checkout";
  return identityFromProvenance({
    productVersion: version,
    mode: mode === "dev" ? "dev" : "build",
    gitSha: conflict ? null : (validPinned || git.sha),
    dirty: Boolean(git.dirty || conflict),
    source,
  });
}
