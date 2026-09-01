import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const designContract = fs.readFileSync(new URL("../app/operator-ui/operator-design-contract.css", import.meta.url), "utf8");
const operatorPanel = fs.readFileSync(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
const operatorPanelCss = fs.readFileSync(new URL("../app/operator-ui/operator-panel.css", import.meta.url), "utf8");
const batchSummaryCss = fs.readFileSync(new URL("../app/operator-ui/batch-summary.css", import.meta.url), "utf8");
const operatorLogCss = fs.readFileSync(new URL("../app/operator-ui/operator-log-panel.css", import.meta.url), "utf8");
const sharedComponent = fs.readFileSync(new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const emodeSession = fs.readFileSync(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
const emodeCss = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");
const emodeBase = fs.readFileSync(new URL("../app/engineering/programming-workspace-base.css", import.meta.url), "utf8");
const emodeDensity = fs.readFileSync(new URL("../app/engineering/engineering-density.css", import.meta.url), "utf8");
const emodeRefresh = fs.readFileSync(new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url), "utf8");
const directApi = fs.readFileSync(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const batchApi = fs.readFileSync(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");
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

test("Operator UI exposes one canonical first-level Panel Header and Toggle owner", () => {
  const expectedTokens = [
    ["--operator-panel-radius", "7px"],
    ["--operator-panel-header-min-height", "30px"],
    ["--operator-panel-title-font-size", "11px"],
    ["--operator-panel-meta-font-size", "8px"],
    ["--operator-field-label-font-size", "11px"],
    ["--operator-helper-font-size", "8px"],
    ["--operator-control-min-height", "32px"],
    ["--operator-control-font-size", "10px"],
    ["--operator-checkbox-size", "14px"],
    ["--operator-action-min-height", "40px"],
    ["--operator-action-font-size", "11px"],
    ["--operator-status-value-font-size", "12px"],
  ];
  for (const [name, value] of expectedTokens) {
    assert.match(designContract, new RegExp(`${name}:\\s*${value.replace(".", "\\.")}`));
  }

  assert.match(operatorPanel, /export function OperatorPanelHeader/);
  assert.match(operatorPanel, /export function OperatorPanelToggle/);
  assert.match(operatorPanelCss, /\.operatorPanelHeader,[\s\S]*\.productionProgrammingCard > header/);
  assert.match(operatorPanelCss, /\.operatorPanelTitle > span,[\s\S]*\.operatorPanelTitle > strong,[\s\S]*\.productionProgrammingCard > header/);
  assert.match(operatorPanelCss, /font-size:\s*var\(--operator-panel-title-font-size\)/);
  assert.match(operatorPanelCss, /font-weight:\s*900/);
  assert.match(operatorPanelCss, /\.operatorPanelToggle,[\s\S]*\.selectionVisibilityButton,[\s\S]*\.engineeringPanelToggle/);

  for (const css of [batchSummaryCss, operatorLogCss, sharedCss]) {
    assert.doesNotMatch(css, /operatorPanelTitle[^\{]*\{|operatorPanelHeader[^\{]*\{[\s\S]*font-size:\s*var\(--operator-panel-title-font-size\)/);
  }
  assert.doesNotMatch(sharedCss, /programmingJobCollapseButton/);
  assert.doesNotMatch(emodeCss, /\.engineeringPanelToggle\s*\{/);
  assert.doesNotMatch(emodeBase, /\.productionProgrammingCard > header\s*\{/);
});

test("Programming Job keeps approved body structure without owning Panel Header presentation", () => {
  assert.match(sharedComponent, /import \{ OperatorPanel, OperatorPanelToggle \} from "\.\/operator-panel"/);
  assert.match(sharedComponent, /<OperatorPanelToggle/);
  assert.match(sharedCss, /\.programmingJobField\s*\{[\s\S]*grid-template-columns:\s*128px minmax\(0, 1fr\)/);
  assert.match(sharedCss, /\.programmingJobField > strong\s*\{[\s\S]*font-size:\s*var\(--operator-field-label-font-size\)/);
  assert.match(sharedCss, /\.programmingJobImageControl\s*\{[\s\S]*min-height:\s*var\(--operator-control-min-height\)/);
  assert.match(sharedCss, /\.programmingJobOperationChecks input\s*\{[\s\S]*width:\s*var\(--operator-checkbox-size\)/);
  assert.match(sharedCss, /\.programmingJobPolicyControls input,[\s\S]*\.programmingJobPolicyControls select\s*\{[\s\S]*min-height:\s*var\(--operator-control-min-height\)/);
  assert.match(sharedCss, /\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1\.08fr\) minmax\(0, 1fr\)/);
  assert.match(sharedCss, /\.programmingJobStart,[\s\S]*\.programmingJobAbort\s*\{[\s\S]*min-height:\s*var\(--operator-action-min-height\)/);
  assert.match(sharedCss, /\.programmingJobStatus\s*\{[\s\S]*min-height:\s*var\(--operator-action-min-height\)/);
  assert.doesNotMatch(sharedCss, /\.programmingJobPanel > \.operatorPanelHeader|\.programmingJobCollapseButton/);
  assert.doesNotMatch(sharedCss, /min-height:\s*(?:56|64)px/);
  assert.doesNotMatch(sharedCss, /font-size:\s*(?:14|15|17|18)px/);
});

test("mode-local styles cannot re-own retired Programming Job or first-level Panel Header presentation", () => {
  assert.doesNotMatch(pmodCss, /\.factoryProgrammingJob|\.factoryJobGrid|\.factoryField|\.factoryImageControl|\.factoryPolicyControls|\.factoryActionBar|\.factoryBatchStatus/);
  assert.doesNotMatch(pmodCss, /\.selectionVisibilityButton\s*\{[\s\S]*font-size:|\.selectionVisibilityButton\s*,[\s\S]*font-size:/);
  assert.doesNotMatch(emodeCss, /\.productionProgrammingCard > header|\.engineeringPanelToggle\s*\{/);
  assert.doesNotMatch(emodeBase, /\.productionProgrammingCard > header\s*\{/);
  assert.doesNotMatch(emodeRefresh, /font-size:\s*0|content:\s*"1\. SYSTEM SETUP|content:\s*"3\. LIVE SITE STATUS/);
});

test("pre-launch Programming UI retains no hidden legacy Read range ownership", () => {
  assert.doesNotMatch(sharedComponent, /compatibilityFields|programmingJobCompatibility/);
  assert.doesNotMatch(emode, /compatibilityFields|engineeringReadRow|Engineering READ offset|Engineering READ length/);
  assert.doesNotMatch(emodeSession, /emodeReadOffset|emodeReadLength|setEmodeReadOffset|setEmodeReadLength/);
  assert.doesNotMatch(emode, /ENGINEERING_READ_OFFSET|ENGINEERING_READ_LENGTH|readOffset:|readLength:/);
  assert.doesNotMatch(pmod, /readOffset:|readLength:/);
  assert.doesNotMatch(directApi, /offset\?:\s*number|length\?:\s*number|body\.offset\s*=|body\.length\s*=/);
  assert.doesNotMatch(batchApi, /readOffset\?:\s*number|readLength\?:\s*number|options\.readOffset|options\.readLength/);
  assert.doesNotMatch(emode, /recentEvents|RECENT EVENTS|Engineering recent events/);

  for (const css of [emodeCss, emodeDensity, emodeRefresh]) {
    assert.doesNotMatch(css, /programmingJobBody|programmingJobCard|engineeringReadRow|recentEvents/);
  }
});
