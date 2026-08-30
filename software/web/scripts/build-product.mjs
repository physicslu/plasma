import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const vinextPackagePath = resolve(projectRoot, "node_modules", "vinext", "package.json");
const vinextPackage = JSON.parse(readFileSync(vinextPackagePath, "utf8"));
const vinextBin =
  typeof vinextPackage.bin === "string" ? vinextPackage.bin : vinextPackage.bin?.vinext;
if (typeof vinextBin !== "string" || !vinextBin) {
  throw new Error("vinext package does not expose a vinext CLI entry point");
}
const vinextCli = resolve(dirname(vinextPackagePath), vinextBin);

const result = spawnSync(
  process.execPath,
  [vinextCli, "build"],
  {
    cwd: projectRoot,
    env: {
      ...process.env,
      PLASMA_PRODUCT_BUILD: "1",
    },
    stdio: "inherit",
  },
);

if (result.error) {
  throw result.error;
}
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
