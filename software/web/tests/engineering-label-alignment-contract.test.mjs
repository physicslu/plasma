import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const alignmentPath = new URL("../app/engineering/engineering-alignment.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering desktop labels use a compact right-aligned control rail", async () => {
  const css = await source(alignmentPath);

  for (const contract of [
    "@container engineering-programming (min-width: 761px)",
    ".targetingCard .workflowField {\n    grid-template-columns: 128px minmax(0, 1fr);\n    gap: 8px;",
    ".targetingCard .workflowField > span {\n    justify-self: end;\n    text-align: right;",
    ".programmingJobBody > .jobRow {\n    grid-template-columns: 128px minmax(0, 1fr);\n    gap: 8px;",
    ".programmingJobBody > .jobRow > strong {\n    justify-self: end;\n    text-align: right;",
    ".programmingBatchOperations {\n    grid-template-columns: 128px minmax(0, 1fr);\n    gap: 8px;",
    ".engineeringPolicyRow {\n    grid-template-columns: 128px max-content max-content minmax(118px, max-content);\n    gap: 8px;",
  ]) {
    assert.ok(css.includes(contract), `missing alignment contract: ${contract}`);
  }
});

test("Engineering mobile labels return to natural left alignment and alignment CSS loads last", async () => {
  const [css, page] = await Promise.all([source(alignmentPath), source(pagePath)]);

  assert.ok(css.includes("@media (max-width: 760px)"));
  assert.ok(css.includes("justify-self: start;\n    text-align: left;"));

  const readability = page.indexOf('import "./engineering-readability.css";');
  const alignment = page.indexOf('import "./engineering-alignment.css";');
  assert.ok(readability >= 0 && alignment > readability, "alignment CSS must load after typography/layout layers");
});
