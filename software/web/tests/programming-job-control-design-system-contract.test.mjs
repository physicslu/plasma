import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const sharedCss = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const pmod = fs.readFileSync(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const pmodCss = fs.readFileSync(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
const emode = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const emodeBaseCss = fs.readFileSync(new URL("../app/engineering/programming-workspace-base.css", import.meta.url), "utf8");
const emodeCss = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");

test("Programming Job control presentation is loaded as one shared operator-ui contract", () => {
  assert.match(layout, /operator-ui\/programming-job-controls\.css/);
  assert.match(sharedCss, /PMode is the approved visual baseline/);
  assert.match(sharedCss, /\.factoryOperationChecks/);
  assert.match(sharedCss, /\.engineeringProgrammingV2 \.programmingBatchOperations \.operationChecks/);
  assert.match(sharedCss, /\.factoryActionBar \.factoryStartButton/);
  assert.match(sharedCss, /\.engineeringProgrammingV2 \.programmingActions \.startProgramming/);
});

test("shared operation selectors preserve the approved PMode tile presentation", () => {
  assert.match(sharedCss, /min-height:\s*34px/);
  assert.match(sharedCss, /padding:\s*0 9px/);
  assert.match(sharedCss, /border:\s*1px solid #ced9e2/);
  assert.match(sharedCss, /border-radius:\s*6px/);
  assert.match(sharedCss, /background:\s*#f8fbfd/);
  assert.match(sharedCss, /gap:\s*4px/);
  assert.match(sharedCss, /font-size:\s*9px/);
  assert.match(sharedCss, /font-weight:\s*700/);
  assert.match(sharedCss, /accent-color:\s*#2563eb/);
  assert.match(sharedCss, /@media \(max-width:\s*760px\)[\s\S]*flex-wrap:\s*wrap/);
});

test("shared START and ABORT actions preserve the approved PMode presentation", () => {
  assert.match(sharedCss, /min-height:\s*38px/);
  assert.match(sharedCss, /font-size:\s*10px/);
  assert.match(sharedCss, /font-weight:\s*850/);
  assert.match(sharedCss, /linear-gradient\(180deg, #2f80d4, #1f65aa\)/);
  assert.match(sharedCss, /linear-gradient\(180deg, #df5a5a, #bc3333\)/);
  assert.match(sharedCss, /opacity:\s*\.42/);
});

test("PMode and EMode keep behavior markup while local CSS cannot own equivalent control visuals", () => {
  assert.match(pmod, /className="factoryOperationChecks"/);
  assert.match(pmod, /className="factoryStartButton"/);
  assert.match(pmod, /className="factoryAbortButton"/);
  assert.match(emode, /className="operationChecks"/);
  assert.match(emode, /className="startProgramming executeBatch"/);
  assert.match(emode, /className="abortProgramming cancelBatch"/);

  assert.doesNotMatch(pmodCss, /\.factoryOperationChecks label\s*\{/);
  assert.doesNotMatch(pmodCss, /\.factoryStartButton\s*\{/);
  assert.doesNotMatch(pmodCss, /\.factoryAbortButton\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.operationChecks\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.operationChecks label\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.operationChecks input\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.programmingActions button\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.startProgramming\s*\{/);
  assert.doesNotMatch(emodeBaseCss, /\.abortProgramming\s*\{/);
  assert.doesNotMatch(emodeCss, /\.programmingBatchOperations \.operationChecks/);
  assert.doesNotMatch(emodeCss, /\.programmingActions button\s*\{/);
});
