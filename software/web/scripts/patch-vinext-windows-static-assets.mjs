import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const PINNED_VINEXT_VERSION = "0.0.50";
const VULNERABLE_RELATIVE_PATH = /relativePath:\s*path\.relative\(base,\s*batch\[j\]\),/g;
const FIXED_RELATIVE_PATH = 'relativePath: path.relative(base, batch[j]).split(path.sep).join("/"),';

/**
 * Apply the narrow upstream Windows StaticFileCache separator fix to the
 * version-pinned vinext build input.
 *
 * vinext 0.0.50 stores path.relative() output directly as URL lookup keys.
 * On Windows that output contains backslashes, so /assets/* requests miss the
 * startup cache and return 404 even though SSR succeeds. The upstream fix is
 * to normalize the filesystem-relative path to URL separators at that
 * boundary. Keep this fail-closed and version-pinned until Plasma upgrades to
 * a vinext release that contains the fix natively.
 */
export function patchVinextWindowsStaticAssets(vinextPackagePath) {
  const vinextRoot = dirname(vinextPackagePath);
  const packageJson = JSON.parse(readFileSync(vinextPackagePath, "utf8"));
  if (packageJson.version !== PINNED_VINEXT_VERSION) {
    throw new Error(
      `vinext Windows static-asset compatibility patch is pinned to ${PINNED_VINEXT_VERSION}; ` +
        `installed version is ${String(packageJson.version)}`,
    );
  }

  const target = resolve(vinextRoot, "dist", "server", "static-file-cache.js");
  const source = readFileSync(target, "utf8");

  if (source.includes(FIXED_RELATIVE_PATH)) {
    return target;
  }

  const matches = source.match(VULNERABLE_RELATIVE_PATH) ?? [];
  if (matches.length !== 1) {
    throw new Error(
      `vinext ${PINNED_VINEXT_VERSION} StaticFileCache patch expected exactly one vulnerable ` +
        `path.relative() site, found ${matches.length}: ${target}`,
    );
  }

  const patched = source.replace(VULNERABLE_RELATIVE_PATH, FIXED_RELATIVE_PATH);
  writeFileSync(target, patched, "utf8");
  return target;
}

export { FIXED_RELATIVE_PATH, PINNED_VINEXT_VERSION };
