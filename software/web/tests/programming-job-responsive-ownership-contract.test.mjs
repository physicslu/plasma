import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const component = fs.readFileSync(new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url), "utf8");
const shared = fs.readFileSync(new URL("../app/operator-ui/programming-job-controls.css", import.meta.url), "utf8");
const refresh = fs.readFileSync(new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url), "utf8");
const density = fs.readFileSync(new URL("../app/engineering/engineering-density.css", import.meta.url), "utf8");
const readability = fs.readFileSync(new URL("../app/engineering/engineering-readability.css", import.meta.url), "utf8");
const alignment = fs.readFileSync(new URL("../app/engineering/engineering-alignment.css", import.meta.url), "utf8");
const v2 = fs.readFileSync(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");

test("shared Programming Job has one real three-child action composition", () => {
  assert.match(component, /className="programmingJobActionBar"/);
  assert.equal((component.match(/data-programming-job-action=/g) ?? []).length, 3);
  const start = component.indexOf('data-programming-job-action="start"');
  const status = component.indexOf('data-programming-job-action="status"');
  const abort = component.indexOf('data-programming-job-action="abort"');
  assert.ok(start < status && status < abort);

  assert.match(shared, /\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1\.08fr\) minmax\(0, 1fr\)/);
  assert.doesNotMatch(shared, /\.programmingJobStatus\s*\{[\s\S]*position:\s*absolute/);
  assert.doesNotMatch(shared, /transform:\s*translateX/);
});

test("shared Programming Job fields cannot switch to a mode-local desktop composition", () => {
  assert.match(shared, /\.programmingJobGrid\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(shared, /\.programmingJobField\s*\{[\s\S]*grid-template-columns:\s*clamp\(190px, 15vw, 260px\) minmax\(0, 1fr\)/);

  for (const source of [refresh, density, readability, alignment, v2]) {
    assert.doesNotMatch(source, /\.programmingJobGrid\b/);
    assert.doesNotMatch(source, /\.programmingJobField\b/);
    assert.doesNotMatch(source, /\.programmingJobActionBar\b/);
    assert.doesNotMatch(source, /\.programmingJobStatus\b/);
    assert.doesNotMatch(source, /\.programmingJobOperationChecks\b/);
    assert.doesNotMatch(source, /\.programmingJobPolicyControls\b/);
  }
});

test("mobile stacking remains owned by the shared component stylesheet", () => {
  assert.match(shared, /@media \(max-width:\s*760px\)[\s\S]*\.programmingJobField\s*\{[\s\S]*grid-template-columns:\s*1fr/);
  assert.match(shared, /@media \(max-width:\s*760px\)[\s\S]*\.programmingJobActionBar\s*\{[\s\S]*grid-template-columns:\s*1fr/);
});
