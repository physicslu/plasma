import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const apiSource = await readFile(new URL("../app/mock-runtime-api.ts", import.meta.url), "utf8");
const pageSource = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const panelSource = await readFile(new URL("../app/engineering/mock-runtime-settings.tsx", import.meta.url), "utf8");
const batchSource = await readFile(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");

test("Mock runtime settings are server-owned and exposed under Engineering", () => {
  assert.match(apiSource, /\/api\/mock\/runtime/);
  assert.match(apiSource, /method: "POST"/);
  assert.match(pageSource, /MockRuntimeSettingsPanel/);
  assert.match(pageSource, /\["mock", "engineering\.settings"\]/);
});

test("Mock UI preserves the 0.1 percent and 4 MiB configuration contract", () => {
  assert.match(panelSource, /step=\{0\.1\}/);
  assert.match(panelSource, /max=\{4096\}/);
  assert.match(panelSource, /Applied Configuration/);
  assert.match(panelSource, /error_rate_per_mille: Math\.round\(Number\(event\.target\.value\) \* 10\)/);
});

test("server Batch snapshots expose immutable Mock execution provenance", () => {
  assert.match(batchSource, /mock_runtime\?: MockBatchRuntimeSnapshot/);
  assert.match(apiSource, /resolved_seed: number/);
  assert.match(apiSource, /revision: number/);
});
