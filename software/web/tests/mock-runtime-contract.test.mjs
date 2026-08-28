import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const apiSource = await readFile(new URL("../app/mock-runtime-api.ts", import.meta.url), "utf8");
const pageSource = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const panelSource = await readFile(new URL("../app/engineering/mock-runtime-settings.tsx", import.meta.url), "utf8");
const mockRuntimeCss = await readFile(new URL("../app/engineering/mock-runtime-settings.css", import.meta.url), "utf8");
const sharedSettingsUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const sharedSettingsCss = await readFile(new URL("../app/operator-ui/settings-ui.css", import.meta.url), "utf8");
const batchSource = await readFile(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");

test("Mock runtime settings are server-owned and exposed under Engineering Settings", () => {
  assert.match(apiSource, /\/api\/mock\/runtime/);
  assert.match(apiSource, /method: "POST"/);
  assert.match(pageSource, /MockRuntimeSettingsPanel/);
  assert.doesNotMatch(pageSource, /\["mock", "engineering\.settings",\s*"◇"\]/);
  assert.match(pageSource, /type SettingsSection = "gateway" \| "mock"/);
  assert.match(pageSource, /className="engineeringNavTreeGroup"/);
  assert.match(pageSource, /aria-expanded=\{settingsExpanded\}/);
  assert.match(pageSource, /selectSettingsSection\("gateway"\)/);
  assert.match(pageSource, /selectSettingsSection\("mock"\)/);
  assert.match(pageSource, /settingsSurfaceActive = active === "settings"/);
});

test("Mock UI preserves the 0.1 percent and 4 MiB configuration contract", () => {
  assert.match(panelSource, /step=\{0\.1\}/);
  assert.match(panelSource, /max=\{4096\}/);
  assert.match(panelSource, /Applied Configuration/);
  assert.match(panelSource, /error_rate_per_mille: Math\.round\(Number\(event\.target\.value\) \* 10\)/);
});

test("Mock settings page uses the shared Settings UI primitives", () => {
  for (const primitive of ["SettingsPage", "SettingsCard", "SettingsGrid", "SettingsField", "SettingsActions", "SettingsMessage", "SettingsMetaGrid", "SettingsGuide"]) {
    assert.match(panelSource, new RegExp(primitive));
    assert.match(sharedSettingsUi, new RegExp(`export function ${primitive}`));
  }
  assert.match(mockRuntimeCss, /\.mockOperationTable/);
  assert.doesNotMatch(mockRuntimeCss, /\.mockRuntimeHeader|\.mockRevisionBadge|\.mockRuntimeGuide|\.mockRuntimeActions|\.mockAppliedMeta/);
});

test("Mock settings page includes operator explanation and test methods", () => {
  assert.match(panelSource, /ariaLabel="Mock Settings Guide"/);
  assert.match(panelSource, /Mock 設定說明/);
  assert.match(panelSource, /基本 PASS 測試/);
  assert.match(panelSource, /Program Error Rate 設為 100\.0%/);
  assert.match(panelSource, /不能宣稱 Z2、FPGA、socket、OpenOCD 或真實 IC programming 已驗證/);
});

test("Mock and Gateway test methods share one explicit numbering contract", () => {
  assert.match(sharedSettingsCss, /counter-reset:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /counter-increment:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /content:\s*counter\(settings-test-step\)\s*"："/);
  assert.match(sharedSettingsCss, /list-style:\s*none/);
});

test("server Batch snapshots expose immutable Mock execution provenance", () => {
  assert.match(batchSource, /mock_runtime\?: MockBatchRuntimeSnapshot/);
  assert.match(apiSource, /resolved_seed: number/);
  assert.match(apiSource, /revision: number/);
});
