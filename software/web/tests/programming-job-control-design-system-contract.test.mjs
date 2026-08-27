import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const sharedComponent = fs.readFileSync(new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

test("PMode and EMode render the same ProgrammingJobPanel component", () => {
  assert.match(layout, /operator-ui\/programming-job-controls\.css/);
  assert.match(pmod, /import \{ ProgrammingJobPanel \} from "\.\.\/operator-ui\/programming-job-panel"/);
  assert.match(emode, /import \{ ProgrammingJobPanel \} from "\.\.\/operator-ui\/programming-job-panel"/);
  assert.equal((pmod.match(/<ProgrammingJobPanel\b/g) ?? []).length, 1);
  assert.equal((emode.match(/<ProgrammingJobPanel\b/g) ?? []).length, 1);
  assert.match(pmod, /<ProgrammingJobPanel[\s\S]*mode="production"/);
  assert.match(emode, /<ProgrammingJobPanel[\s\S]*mode="engineering"/);
});

test("shared component owns all four Programming Job fields", () => {
  for (const field of ["target", "image", "operations", "policy"]) {
    assert.match(sharedComponent, new RegExp(`data-programming-job-field="${field}"`));
  }
  assert.match(sharedComponent, /className="programmingJobImageControl"/);
  assert.match(sharedComponent, /className="programmingJobOperationChecks"/);
  assert.match(sharedComponent, /className="programmingJobPolicyControls"/);
});

test("shared action bar structurally owns START then STATUS then ABORT", () => {
  const start = sharedComponent.indexOf('data-programming-job-action="start"');
  const status = sharedComponent.indexOf('data-programming-job-action="status"');
  const abort = sharedComponent.indexOf('data-programming-job-action="abort"');
  assert.ok(start >= 0, "shared START action is required");
  assert.ok(status > start, "shared STATUS must follow START");
  assert.ok(abort > status, "shared ABORT must follow STATUS");
  assert.match(sharedComponent, /className="programmingJobActionBar"/);

  assert.doesNotMatch(pmod, /className="factoryActionBar"/);
  assert.doesNotMatch(pmod, /className="factoryBatchStatus/);
  assert.doesNotMatch(emode, /className=`?\{?`?batchReadiness/);
  assert.doesNotMatch(emode, /className="programmingActions"/);
});

test("shared presentation preserves the approved PMode controls", () => {
  assert.match(sharedCss, /\.programmingJobOperationChecks label\s*\{[\s\S]*height:\s*34px/);
  assert.match(sharedCss, /\.programmingJobOperationChecks input\s*\{[\s\S]*width:\s*14px/);
  assert.match(sharedCss, /\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 160px minmax\(0, 1fr\)/);
  assert.match(sharedCss, /\.programmingJobStart,[\s\S]*\.programmingJobAbort\s*\{[\s\S]*min-height:\s*38px/);
  assert.match(sharedCss, /linear-gradient\(180deg, #2f80d4, #1f65aa\)/);
  assert.match(sharedCss, /linear-gradient\(180deg, #df5a5a, #bc3333\)/);
  assert.match(sharedCss, /\.programmingJobStatus\s*\{[\s\S]*min-height:\s*38px/);
});
