import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");

test("BFF allowlists only the PPU-scoped run status / acknowledge routes; no single plan or run", async () => {
  const bff = await read("app/api/manager/bootstrap-bff.ts");
  // U2: the single plan + run retired; every Job is a Manager Batch attempt.
  assert.doesNotMatch(bff, /\/\^programming\\\/plans\$\//);
  assert.doesNotMatch(bff, /\/\^programming\\\/runs\$\//);
  assert.match(bff, /`\^programming\/runs\/\$\{RUN_ID\}\/acknowledge\$`/);
  assert.match(bff, /`\^programming\/runs\/\$\{RUN_ID\}\$`/);
  assert.match(bff, /\/\^programming\\\/routes\$\//);
  assert.match(bff, /const RUN_ID = "\[0-9a-f\]\{32\}"/);
  // Programming POSTs ride the existing maintenance capability boundary.
  assert.match(bff, /normalizedAction !== "enrollment" && !hasMaintenanceCapability\(request, normalizedAlias\)/);
  assert.doesNotMatch(bff, /programming\/(retry|resubmit)/);
});

test("Browser never builds/signs a Bundle or talks to the PPU directly", async () => {
  const api = await read("app/engineering/bundle-programming-api.ts");
  const ui = await read("app/engineering/bundle-programming.tsx");
  for (const source of [api, ui]) {
    assert.doesNotMatch(source, /manifest\.json|zip|owner_authorization|authorization:/i);
    assert.doesNotMatch(source, /\/api\/manager\/ppu\/api\/jobs|:18080|:18081|\/v1\//);
  }
  assert.match(api, /\/api\/manager\/registry\/\$\{encodeURIComponent\(alias\)\}\/bootstrap\/programming/);
  assert.doesNotMatch(api, /\/plans`|PROGRAMMING_CONFIRM_TOKEN|function (planProgramming|startProgramming)\(/);
});

test("Console starts one Manager Batch at most once and never auto-resubmits", async () => {
  const ui = await read("app/engineering/bundle-programming.tsx");
  assert.match(ui, /if \(startedRef\.current\) return;/);
  // U2: programming and Read Memory are each one Manager Batch (one Site, one Cycle).
  assert.equal((ui.match(/runManagedBatch\(/g) ?? []).length, 1);
  assert.equal((ui.match(/runManagedRead\(/g) ?? []).length, 1);
  assert.match(ui, /retryLimit: 0, stopPolicy: \{ kind: "never" \}/);
  assert.doesNotMatch(ui, /planProgramming|startProgramming\(/);
  // The run / receipt / OUTCOME_UNKNOWN view is the one shared with EMode and PMode.
  const view = await read("app/operator-ui/programming-run-view.tsx");
  assert.match(ui, /<ProgrammingRunView run=\{run\}/);
  assert.match(view, /Nothing was resubmitted/);
  assert.match(view, /Acknowledge reconciliation/);
  // Catalog Level is a display filter only for programming.
  assert.match(ui, /const PICKER_LEVELS: Array<1 \| 2 \| 3> = \[1, 2, 3\]/);
});

test("Programming panel is mounted on the Platform page for commissioned PPUs", async () => {
  const page = await read("app/engineering/ppu-runtime-deployment-page.tsx");
  assert.match(page, /selectedEntry\.lifecycle === "commissioned" && \(\s*<BundleProgramming/);
});
