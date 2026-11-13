import { access, readdir, readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, relative, resolve, sep } from "node:path";
import { buildIdentityForVite } from "../build/build-identity.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const standaloneRoot = resolve(projectRoot, "dist", "standalone");
const serverEntry = resolve(standaloneRoot, "server.js");

await access(serverEntry);
const serverInfo = await stat(serverEntry);
if (!serverInfo.isFile() || serverInfo.size <= 0) {
  throw new Error("dist/standalone/server.js must be a non-empty file");
}

const forbiddenBasenames = new Set([
  ".env",
  "package-lock.json",
  "pnpm-lock.yaml",
  "yarn.lock",
  "vite.config.ts",
  "next.config.ts",
]);
const forbiddenSegments = new Set([".git", "tests", ".wrangler"]);

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    const rel = relative(standaloneRoot, path);
    const segments = rel.split(sep);
    if (segments.some((segment) => forbiddenSegments.has(segment))) {
      throw new Error(`standalone runtime contains source/development path: ${rel}`);
    }
    if (forbiddenBasenames.has(entry.name) || entry.name.startsWith(".env.")) {
      throw new Error(`standalone runtime contains prohibited source/config file: ${rel}`);
    }
    if (entry.isDirectory()) {
      await walk(path);
    }
  }
}

await walk(standaloneRoot);

if (process.env.PLASMA_REQUIRE_BUILD_IDENTITY === "1") {
  const identity = buildIdentityForVite({ mode: "build" });
  if (identity.mode !== "build") {
    throw new Error("Render product validation requires a clean, matching Git SHA");
  }
  const clientAssets = resolve(standaloneRoot, "dist", "client", "assets");
  const assets = (await readdir(clientAssets)).filter(name => name.endsWith(".js"));
  let embedded = false;
  for (const name of assets) {
    const source = await readFile(resolve(clientAssets, name), "utf8");
    if (source.includes(identity.gitSha) && source.includes(identity.releaseId)) {
      embedded = true;
      break;
    }
  }
  if (!embedded) throw new Error("Render frontend bundle is missing its full SHA and Release ID");
}

const sourceRootText = projectRoot.replaceAll("\\", "/");
const serverText = (await readFile(serverEntry, "utf8")).replaceAll("\\", "/");
if (serverText.includes(sourceRootText)) {
  throw new Error("standalone server entry embeds the source-tree absolute path");
}

console.log(`Validated Control Station standalone Web runtime: ${standaloneRoot}`);
