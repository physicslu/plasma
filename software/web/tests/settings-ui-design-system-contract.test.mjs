import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const sharedUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const sharedCss = await readFile(new URL("../app/operator-ui/settings-ui.css", import.meta.url), "utf8");
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

test("Gateway composition follows the approved Mock Settings reference", () => {
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

test("Shared Settings UI owns Mock-reference cards, controls, actions, guide typography and numbering", () => {
  assert.match(sharedCss, /\.settingsCard,[\s\S]*\.settingsGuide/);
  assert.match(sharedCss, /--settings-control-height:\s*40px/);
  assert.match(sharedCss, /--settings-action-height:\s*40px/);
  assert.match(sharedCss, /\.settingsPage input:not\(\[type="checkbox"\]\),[\s\S]*height:\s*var\(--settings-control-height\)/);
  assert.match(sharedCss, /\.settingsActions button\s*\{[\s\S]*min-height:\s*var\(--settings-action-height\)/);
  assert.match(sharedCss, /\.settingsActions button\[data-variant="primary"\]/);
  assert.match(sharedCss, /\.settingsGuide > header p,[\s\S]*font-size:\s*14px;[\s\S]*line-height:\s*1\.7/);
  assert.match(sharedCss, /counter-reset:\s*settings-test-step/);
  assert.match(sharedCss, /content:\s*counter\(settings-test-step\)\s*"："/);
});
