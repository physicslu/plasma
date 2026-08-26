import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Engineering Programming owns its base stylesheet directly", async () => {
  const workspace = await source("../app/engineering/programming-workspace-v2.tsx");

  assert.match(workspace, /import "\.\/programming-workspace-base\.css";/);
  assert.doesNotMatch(workspace, /\.\.\/fleet\/programming\//);
});

test("retired Production Programming CSS compatibility shim stays removed", async () => {
  await assert.rejects(
    fs.access(new URL("../app/fleet/programming/production-programming.css", import.meta.url)),
  );
});
