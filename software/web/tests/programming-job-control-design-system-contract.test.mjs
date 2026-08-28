import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const sharedComponent = fs.readFileSync(new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const sharedDriver = fs.readFileSync(new URL("../e2e/tests/programming-job-test-helpers.ts", import.meta.url), "utf8");
const productionRuntime = fs.readFileSync(new URL("../e2e/tests/production-multi-ppu-runtime.spec.ts", import.meta.url), "utf8");
const engineeringRuntime = fs.readFileSync(new URL("../e2e/tests/engineering-programming-asset-cache-runtime.spec.ts", import.meta.url), "utf8");

test("PMode and EMode render the same ProgrammingJobPanel component", () => {
  assert.doesNotMatch(layout, /operator-ui\/programming-job-controls\.css/);
  assert.match(sharedComponent, /import "\.\/programming-job-controls\.css"/);
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

test("shared component exposes semantic operation, policy and action test hooks", () => {
  assert.match(sharedComponent, /data-programming-job-operation=\{operation\.key\}/);
  for (const policy of ["repeat", "retry", "stop"]) {
    assert.match(sharedComponent, new RegExp(`data-programming-job-policy="${policy}"`));
  }
  for (const action of ["start", "status", "abort"]) {
    assert.match(sharedComponent, new RegExp(`data-programming-job-action="${action}"`));
  }
});

test("PMode and EMode runtime tests consume one Programming Job test driver", () => {
  assert.match(sharedDriver, /expectedFields:[^\n]*\["target", "image", "operations", "policy"\]/);
  assert.match(sharedDriver, /expectedActions:[^\n]*\["start", "status", "abort"\]/);
  assert.match(sharedDriver, /expectedOperations:[^\n]*\["erase", "program", "verify", "read"\]/);
  assert.match(sharedDriver, /expectedPolicies:[^\n]*\["repeat", "retry", "stop"\]/);
  assert.match(sharedDriver, /export async function expectProgrammingJobContract/);
  assert.match(sharedDriver, /export function programmingJobOperation/);
  assert.match(sharedDriver, /export function programmingJobAction/);

  assert.match(productionRuntime, /from "\.\/programming-job-test-helpers"/);
  assert.match(productionRuntime, /programmingJob\(page, "production"\)/);
  assert.match(engineeringRuntime, /from "\.\/programming-job-test-helpers"/);
  assert.match(engineeringRuntime, /programmingJob\(page, "engineering"\)/);
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

test("shared presentation owns the approved Programming Job card", () => {
  assert.match(sharedCss, /\.programmingJobPanel\s*\{[\s\S]*border-radius:\s*10px/);
  assert.match(sharedCss, /\.programmingJobPanel > \.operatorPanelHeader\s*\{[\s\S]*min-height:\s*56px/);
  assert.match(sharedCss, /\.programmingJobField\s*\{[\s\S]*border-bottom:\s*1px solid/);
  assert.match(sharedCss, /grid-template-columns:\s*clamp\(190px, 15vw, 260px\) minmax\(0, 1fr\)/);
  assert.match(sharedCss, /\.programmingJobField > strong\s*\{[\s\S]*justify-self:\s*start[\s\S]*text-align:\s*left/);
  assert.match(sharedCss, /\.programmingJobImageControl\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 144px/);
  assert.match(sharedCss, /\.programmingJobOperationChecks label\s*\{[\s\S]*border:\s*0[\s\S]*background:\s*transparent/);
  assert.match(sharedCss, /\.programmingJobOperationChecks input\s*\{[\s\S]*width:\s*18px/);
  assert.match(sharedCss, /\.programmingJobPolicyControls input\s*\{[\s\S]*width:\s*138px/);
  assert.match(sharedCss, /\.programmingJobPolicyControls select\s*\{[\s\S]*min-width:\s*190px/);
  assert.match(sharedCss, /\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1\.08fr\) minmax\(0, 1fr\)/);
  assert.match(sharedCss, /\.programmingJobStart,[\s\S]*\.programmingJobAbort\s*\{[\s\S]*min-height:\s*64px/);
  assert.match(sharedCss, /linear-gradient\(180deg, #1768c7, #0c51a9\)/);
  assert.match(sharedCss, /linear-gradient\(180deg, #cf3838, #ba2929\)/);
  assert.match(sharedCss, /\.programmingJobStatus\s*\{[\s\S]*min-height:\s*64px/);
});
