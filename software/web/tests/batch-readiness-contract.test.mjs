import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const root = new URL("../app/", import.meta.url);

async function read(path) {
  return fs.readFile(new URL(path, root), "utf8");
}

test("Pmod and Emode share one batch readiness source of truth", async () => {
  const readiness = await read("batch-readiness.ts");
  const pmodRoute = await read("fleet/page.tsx");
  const pmod = await read("fleet/server-batch-page.tsx");
  const emode = await read("engineering/programming-workspace.tsx");

  for (const label of [
    "BATCH READY",
    "NO TARGET",
    "NO SITE",
    "NO OP",
    "IMAGE REQUIRED",
    "IMAGE INVALID",
    "INVALID READ",
    "PPU OFFLINE",
    "SITE BUSY",
    "RUNNING",
    "CANCELLING",
  ]) assert.match(readiness, new RegExp(label.replace(/ /g, "\\s")));

  assert.match(readiness, /export function evaluateBatchReadiness/);
  assert.match(pmodRoute, /server-batch-page/);
  assert.match(pmod, /evaluateBatchReadiness\(/);
  assert.match(emode, /evaluateBatchReadiness\(/);
  assert.match(pmod, /disabled=\{!batchReadiness\.ready \|\| !policyValid\}/);
  assert.match(emode, /disabled=\{!batchReadiness\.ready\}/);
});

test("Pmod and Emode use the same programming batch toolbar contract", async () => {
  const css = await read("programming-batch-toolbar.css");
  const pmod = await read("fleet/server-batch-page.tsx");
  const emode = await read("engineering/programming-workspace.tsx");

  assert.match(css, /\.programmingFileName[\s\S]*font-size:\s*13px/);
  assert.match(css, /\.programmingBatchOperations[\s\S]*justify-self:\s*end/);
  assert.match(css, /grid-template-areas:\s*"file operations actions"/);
  assert.match(pmod, /productionBatchToolbar programmingBatchToolbar/);
  assert.match(emode, /engineeringExecutionToolbar programmingBatchToolbar/);
  assert.match(pmod, /programmingBatchFile/);
  assert.match(emode, /programmingBatchFile/);
  assert.match(pmod, /programmingBatchOperations/);
  assert.match(emode, /programmingBatchOperations/);
  assert.match(pmod, /programmingBatchActions/);
  assert.match(emode, /programmingBatchActions/);
});

test("Emode density contract matches Pmod upper-page rhythm", async () => {
  const css = await read("engineering/engineering-density.css");
  assert.match(css, /\.engineeringShell\s*\{[\s\S]*padding:\s*18px clamp\(12px, 1\.8vw, 28px\) 36px/);
  assert.match(css, /\.engineeringHeading\s*\{[\s\S]*min-height:\s*54px/);
  assert.match(css, /\.engineeringProgramming\s*\{[\s\S]*gap:\s*6px/);
});
