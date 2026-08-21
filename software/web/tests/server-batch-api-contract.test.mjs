import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const sourceUrl = new URL("../app/server-batch-api.ts", import.meta.url);

test("server Batch client binds Programming Asset only when Program or Verify is selected", async () => {
  const source = await fs.readFile(sourceUrl, "utf8");

  assert.match(source, /const usesAsset = options\.operations\.some\(operation => operation === "program" \|\| operation === "verify"\)/);
  assert.match(source, /const asset = usesAsset && options\.assetFile/);
  assert.match(source, /Programming Asset must not be empty/);
  assert.match(source, /\.\.\.\(asset \? \{ asset \} : \{\}\)/);
});
