import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  FIXED_RELATIVE_PATH,
  patchVinextWindowsStaticAssets,
} from "../scripts/patch-vinext-windows-static-assets.mjs";

async function fixture(version = "0.0.50") {
  const root = await mkdtemp(join(tmpdir(), "plasma-vinext-patch-"));
  const server = join(root, "dist", "server");
  await mkdir(server, { recursive: true });
  const packagePath = join(root, "package.json");
  const target = join(server, "static-file-cache.js");
  await writeFile(packagePath, JSON.stringify({ name: "vinext", version }), "utf8");
  await writeFile(
    target,
    'yield {\n  relativePath: path.relative(base, batch[j]),\n  fullPath: batch[j],\n};\n',
    "utf8",
  );
  return { root, packagePath, target };
}

test("pinned Vinext Windows compatibility patch normalizes static cache URL keys", async () => {
  const { root, packagePath, target } = await fixture();
  try {
    patchVinextWindowsStaticAssets(packagePath);
    const patched = await readFile(target, "utf8");
    assert.match(patched, /split\(path\.sep\)\.join\("\/"\)/);
    assert.ok(patched.includes(FIXED_RELATIVE_PATH));

    // Reapplying the exact patch is idempotent for repeated product validation.
    patchVinextWindowsStaticAssets(packagePath);
    assert.equal(await readFile(target, "utf8"), patched);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Vinext compatibility patch fails closed on an unreviewed version", async () => {
  const { root, packagePath } = await fixture("9.9.9");
  try {
    assert.throws(
      () => patchVinextWindowsStaticAssets(packagePath),
      /compatibility patch is pinned to 0\.0\.50/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
