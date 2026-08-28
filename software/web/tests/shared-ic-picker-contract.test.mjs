import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("PMode and EMode consume one neutral ICPickerField primitive through ProgrammingJobPanel", async () => {
  const [picker, sharedJob, pmod, emode] = await Promise.all([
    source("../app/devices/ic-picker-field.tsx"),
    source("../app/operator-ui/programming-job-panel.tsx"),
    source("../app/fleet/factory-console-v2.tsx"),
    source("../app/engineering/programming-workspace-v2.tsx"),
  ]);

  assert.match(picker, /import "\.\/ic-picker-field\.css"/);
  assert.match(picker, /className="icPicker"/);
  assert.match(picker, /className="icPickerInput"/);
  assert.match(picker, /className="icPickerMenu"/);
  assert.doesNotMatch(picker, /productionIcPicker/);
  assert.match(sharedJob, /ICPickerField/);
  assert.match(pmod, /<ProgrammingJobPanel[\s\S]*mode="production"/);
  assert.match(emode, /<ProgrammingJobPanel[\s\S]*mode="engineering"/);
  assert.match(pmod, /targetDevice=\{targetDevice\}/);
  assert.match(emode, /targetDevice=\{targetDevice\}/);
});

test("shared IC picker stylesheet owns internal visuals and host density profiles", async () => {
  const css = await source("../app/devices/ic-picker-field.css");

  for (const contract of [
    ".icPicker {",
    "font-family: var(--font-sans), Arial, sans-serif;",
    ".icPickerInput {",
    ".icPickerMenu {",
    ".factoryConsoleV2 .icPickerInput {",
    ".factoryConsoleV2 .icPickerMenu {",
    ".engineeringProgrammingV2 .icPickerMenu small {",
    "[data-theme=\"dark\"] .factoryConsoleV2 .icPickerInput,",
  ]) {
    assert.ok(css.includes(contract), `missing shared IC picker contract: ${contract}`);
  }
});

test("mode-local styles cannot own IC picker internals", async () => {
  const [pmodCss, emodeCss] = await Promise.all([
    source("../app/fleet/factory-console-v2.css"),
    source("../app/engineering/programming-workspace-base.css"),
  ]);

  for (const css of [pmodCss, emodeCss]) {
    assert.doesNotMatch(css, /productionIcPicker/);
    assert.doesNotMatch(css, /\.icPicker(?:Input|Menu)?/);
  }
});
