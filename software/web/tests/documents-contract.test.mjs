import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const demo = await readFile(new URL("../app/demo/page.tsx", import.meta.url), "utf8");
const documents = await readFile(new URL("../app/documents/page.tsx", import.meta.url), "utf8");
const documentsCss = await readFile(new URL("../app/documents/documents.css", import.meta.url), "utf8");

test("Documents is the fourth portal function and remains outside Product Mode", () => {
  assert.match(demo, /<span>04<\/span>/);
  assert.match(demo, /href="\/documents"/);
  assert.match(demo, /<h2>\{zh \? "文件" : "Documents"\}<\/h2>/);
  assert.doesNotMatch(documents, /setProductMode|ProductMode/);
});

test("Documents is static operator content with no API or runtime document backend", () => {
  assert.doesNotMatch(documents, /fetch\(/);
  assert.doesNotMatch(documents, /apiBase|\/api\//);
  assert.doesNotMatch(documents, /markdown|remark|rehype/i);
  assert.match(documents, /TopicContent/);
  assert.match(documents, /PMode/);
  assert.match(documents, /EMode/);
});

test("Documents reuses the EMode sidebar presentation instead of defining a second sidebar skin", () => {
  assert.match(documents, /import "\.\.\/engineering\/engineering\.css"/);
  assert.match(documents, /import "\.\.\/engineering\/engineering-workspace-refresh\.css"/);
  assert.match(documents, /className="engineeringSidebar"/);
  assert.match(documents, /className="engineeringNavTreeGroup"/);
  assert.match(documents, /className="engineeringNavChildren"/);
  assert.doesNotMatch(documentsCss, /\.engineeringSidebar\s*\{/);
});

test("Documents v1 covers PMode, EMode, Gateway and Mock operator reference", () => {
  for (const required of [
    "pmode-overview",
    "pmode-flow",
    "pmode-programming",
    "pmode-batch",
    "emode-overview",
    "emode-flow",
    "emode-programming",
    "gateway-settings",
    "mock-settings",
  ]) assert.match(documents, new RegExp(required));

  assert.match(documents, /IC FAIL ≠ Infrastructure ERROR/);
  assert.match(documents, /4 × 10 sec \+ 1 \+ 2 \+ 4 sec = 47 sec/);
  assert.match(documents, /Mock PASS ≠/);
  assert.match(documents, /0\.1%/);
});
