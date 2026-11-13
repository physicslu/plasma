import { access, readdir, readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, relative, resolve, sep } from "node:path";

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

const sourceRootText = projectRoot.replaceAll("\\", "/");
const serverText = (await readFile(serverEntry, "utf8")).replaceAll("\\", "/");
if (serverText.includes(sourceRootText)) {
  throw new Error("standalone server entry embeds the source-tree absolute path");
}

console.log(`Validated Control Station standalone Web runtime: ${standaloneRoot}`);
