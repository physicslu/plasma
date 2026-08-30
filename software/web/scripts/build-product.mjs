import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

const result = spawnSync(
  npmCommand,
  ["exec", "--", "vinext", "build"],
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
