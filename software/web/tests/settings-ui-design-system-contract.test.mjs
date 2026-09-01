import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const sharedUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const sharedCss = await readFile(new URL("../app/operator-ui/settings-ui.css", import.meta.url), "utf8");
const sharedSurfaceCss = await readFile(new URL("../app/operator-ui/operator-surface-primitives.css", import.meta.url), "utf8");
const loopbackCss = await readFile(new URL("../app/engineering/loopback-test.css", import.meta.url), "utf8");
const diagnosticsCss = await readFile(new URL("../app/engineering/diagnostics-test-page.css", import.meta.url), "utf8");
const gateway = await readFile(new URL("../app/engineering/gateway-settings.tsx", import.meta.url), "utf8");
const mock = await readFile(new URL("../app/engineering/mock-runtime-settings.tsx", import.meta.url), "utf8");
const mockCss = await readFile(new URL("../app/engineering/mock-runtime-settings.css", import.meta.url), "utf8");
const page = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");

test("Engineering Settings exposes one canonical shared primitive set", () => {
  for (const primitive of [
    "SettingsPage",
    "SettingsTabs",
    "SettingsCard",
    "SettingsGrid",
    "SettingsField",
    "SettingsActions",
    "SettingsMessage",
    "SettingsMetaGrid",
    "SettingsGuide",
  ]) {
    assert.match(sharedUi, new RegExp(`export function ${primitive}`));
  }
  assert.match(sharedUi, /import "\.\/settings-ui\.css"/);
  assert.match(sharedCss, /@import "\.\/operator-surface-primitives\.css"/);
});

test("Gateway and Mock consume shared Settings UI instead of owning duplicate visual systems", () => {
  assert.match(gateway, /from "\.\.\/operator-ui\/settings-ui"/);
  assert.match(mock, /from "\.\.\/operator-ui\/settings-ui"/);
  assert.doesNotMatch(gateway, /gateway-settings\.css/);

  for (const forbiddenLocalRule of [
    "mockRuntimeHeader",
    "mockRevisionBadge",
    "mockRuntimeGuide",
    "mockRuntimeActions",
    "mockAppliedMeta",
    "mockApplyButton",
  ]) {
    assert.doesNotMatch(mockCss, new RegExp(`\\.${forbiddenLocalRule}`));
  }
  assert.match(mockCss, /\.mockOperationTable/);
});

test("Gateway composition follows the approved shared Settings structure", () => {
  assert.match(mock, /title=\{text\.title\}/);
  assert.match(mock, /subtitle=\{text\.subtitle\}/);
  assert.match(mock, /<SettingsCard ariaLabel="Mock runtime controls">/);
  assert.match(mock, /<SettingsGrid columns=\{3\}>/);

  assert.match(gateway, /title=\{text\.title\}/);
  assert.match(gateway, /subtitle=\{text\.subtitle\}/);
  assert.match(gateway, /<SettingsCard ariaLabel="Gateway Communication Settings">/);
  assert.match(gateway, /<SettingsGrid columns=\{3\}>/);
  assert.doesNotMatch(gateway, /SettingsTabs/);
});

test("Gateway and Mock are child views of the same Settings canvas placement contract", () => {
  assert.match(page, /type SettingsSection = "gateway" \| "mock"/);
  assert.match(page, /settingsSurfaceActive = active === "settings"/);
  assert.match(page, /selectSettingsSection\("gateway"\)/);
  assert.match(page, /selectSettingsSection\("mock"\)/);
  assert.match(page, /settingsSurfaceActive \? "settingsActive"/);
  assert.doesNotMatch(page, /\["mock", "engineering\.settings"/);
});

test("Settings and Loopback share one operator card, field and action presentation owner", () => {
  assert.match(loopbackCss, /@import "\.\.\/operator-ui\/operator-surface-primitives\.css"/);
  assert.match(sharedSurfaceCss, /\.settingsCard,[\s\S]*\.diagnosticsTestCard\s*\{[\s\S]*border-radius:\s*10px[\s\S]*box-shadow:/);
  assert.match(sharedSurfaceCss, /\.settingsField,[\s\S]*\.diagnosticsField\s*\{[\s\S]*gap:\s*6px/);
  assert.match(sharedSurfaceCss, /\.settingsPage input:not\(\[type="checkbox"\]\),[\s\S]*\.diagnosticsField select\s*\{[\s\S]*min-height:\s*36px[\s\S]*border-radius:\s*6px[\s\S]*font:\s*11px var\(--font-mono\)/);
  assert.match(sharedSurfaceCss, /\.settingsActions button,[\s\S]*\.loopbackExecutionActions button\s*\{[\s\S]*min-height:\s*38px[\s\S]*border-radius:\s*6px[\s\S]*font:\s*700 11px\/1\.2 var\(--font-sans\)/);
  assert.match(sharedSurfaceCss, /\.settingsActions button\[data-variant="primary"\],[\s\S]*\.loopbackExecutionActions button\.primary/);

  assert.doesNotMatch(sharedCss, /--settings-control-height|--settings-action-height/);
  assert.doesNotMatch(sharedCss, /\.settingsPage input:not\(\[type="checkbox"\]\),/);
  assert.doesNotMatch(sharedCss, /\.settingsActions button\s*\{/);
  assert.doesNotMatch(loopbackCss, /\.diagnosticsField input,[\s\S]*\.diagnosticsField select\s*\{/);
  assert.doesNotMatch(loopbackCss, /\.loopbackExecutionActions button\s*\{/);
  assert.doesNotMatch(diagnosticsCss, /\.diagnosticsTestCard\s*\{/);
});

test("Shared Settings UI retains Settings-specific guide typography and numbering", () => {
  assert.match(sharedCss, /\.settingsGuide > header p,[\s\S]*font-size:\s*14px;[\s\S]*line-height:\s*1\.7/);
  assert.match(sharedCss, /counter-reset:\s*settings-test-step/);
  assert.match(sharedCss, /content:\s*counter\(settings-test-step\)\s*"："/);
});
