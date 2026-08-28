import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const alignmentPath = new URL("../app/engineering/engineering-alignment.css", import.meta.url);
const programmingJobPath = new URL("../app/operator-ui/programming-job-controls.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering desktop alignment owns only the compact targeting rail", async () => {
  const [css, programmingJobCss] = await Promise.all([
    source(alignmentPath),
    source(programmingJobPath),
  ]);

  for (const contract of [
    "@container engineering-programming (min-width: 761px)",
    ".targetingCard .workflowField {\n    grid-template-columns: 112px minmax(0, 1fr);\n    gap: 8px;",
    ".targetingCard .workflowField > span {\n    justify-self: end;\n    text-align: right;",
  ]) {
    assert.ok(css.includes(contract), `missing targeting alignment contract: ${contract}`);
  }

  for (const forbidden of [
    ".programmingJobBody",
    ".programmingBatchOperations",
    ".engineeringPolicyRow",
    ".programmingJobField",
  ]) {
    assert.ok(!css.includes(forbidden), `Engineering alignment must not own shared Programming Job selector: ${forbidden}`);
  }

  assert.ok(programmingJobCss.includes(".programmingJobField {"));
  assert.ok(programmingJobCss.includes("grid-template-columns: 128px minmax(0, 1fr);"));
  assert.ok(programmingJobCss.includes("column-gap: 8px;"));
  assert.ok(programmingJobCss.includes("justify-self: start;\n  text-align: left;"));
  assert.equal(programmingJobCss.includes("clamp(190px, 15vw, 260px)"), false);
});

test("Engineering mobile targeting labels return to natural left alignment and alignment CSS loads last", async () => {
  const [css, page] = await Promise.all([source(alignmentPath), source(pagePath)]);

  assert.ok(css.includes("@media (max-width: 760px)"));
  assert.ok(css.includes(".targetingCard .workflowField > span"));
  assert.ok(css.includes("justify-self: start;\n    text-align: left;"));

  const readability = page.indexOf('import "./engineering-readability.css";');
  const alignment = page.indexOf('import "./engineering-alignment.css";');
  assert.ok(readability >= 0 && alignment > readability, "alignment CSS must load after typography/layout layers");
});
