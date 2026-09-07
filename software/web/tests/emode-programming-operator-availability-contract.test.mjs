import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const css = await readFile(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");
const workspace = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("EMode keeps provider implementation details out of the operator availability surface", () => {
  assert.match(css, /engineeringBoundaryNote\.warning > span[\s\S]*display:\s*none/);
  assert.match(workspace, /appendLog\(`\[ENGINEERING\] Programming unavailable · \$\{message\}`/);
  assert.match(workspace, /<b>\{programmingUnavailableLabel\}<\/b><span>\{catalogError\}<\/span>/);
});
