import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const operatorSurface = await readFile(new URL("../app/operator-ui/operator-surface.tsx", import.meta.url), "utf8");
const sharedCss = await readFile(new URL("../app/operator-ui/operator-surface-primitives.css", import.meta.url), "utf8");
const settingsUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const diagnosticsUi = await readFile(new URL("../app/engineering/diagnostics-test-page.tsx", import.meta.url), "utf8");
const siteDesiredUi = await readFile(new URL("../app/engineering/ppu-site-desired-configuration.tsx", import.meta.url), "utf8");
const siteDesiredCore = await readFile(new URL("../app/engineering/ppu-site-desired-configuration-core.tsx", import.meta.url), "utf8");
const runtimeActivationUi = await readFile(new URL("../app/engineering/ppu-runtime-activation.tsx", import.meta.url), "utf8");

test("operator-ui exposes narrow reusable component primitives", () => {
  for (const primitive of [
    "OperatorCard",
    "OperatorField",
    "OperatorActions",
    "OperatorButton",
    "OperatorMessage",
  ]) {
    assert.match(operatorSurface, new RegExp(`export function ${primitive}`));
  }

  assert.doesNotMatch(operatorSurface, /LoopbackEndpoint|PPUSiteDesired|ManagerRegistryEntry|SettingsGuide/);
});

test("Settings composition delegates common structure to operator primitives", () => {
  assert.match(settingsUi, /from "\.\/operator-surface"/);
  assert.match(settingsUi, /<OperatorCard className=\{joinClasses\("settingsCard", className\)\}/);
  assert.match(settingsUi, /<OperatorField[\s\S]*className=\{joinClasses\("settingsField", className\)\}/);
  assert.match(settingsUi, /<OperatorActions className="settingsActions">/);
  assert.match(settingsUi, /<OperatorMessage className="settingsMessage"/);
});

test("Diagnostics and PPU Site Desired reuse operator components without sharing workflow logic", () => {
  assert.match(diagnosticsUi, /from "\.\.\/operator-ui\/operator-surface"/);
  assert.match(diagnosticsUi, /<OperatorCard className=\{`diagnosticsTestCard/);

  assert.match(siteDesiredUi, /PpuSiteDesiredConfigurationCore/);
  assert.match(siteDesiredUi, /PpuRuntimeActivation/);
  assert.match(siteDesiredCore, /from "\.\.\/operator-ui\/operator-surface"/);
  assert.match(siteDesiredCore, /<OperatorCard className="ppuSiteCard" ariaLabel="Programming Site Configuration">/);
  assert.match(siteDesiredCore, /<OperatorActions className="ppuSiteCardHeaderActions">/);
  assert.match(siteDesiredCore, /<OperatorButton[\s\S]*variant="primary"/);
  assert.match(siteDesiredCore, /<OperatorMessage className="ppuRegistryMessage error" tone="error"/);
  assert.match(runtimeActivationUi, /from "\.\.\/operator-ui\/operator-surface"/);

  assert.doesNotMatch(operatorSurface, /desired_revision|If-Match|restart_required|runtime_apply_supported/);
});

test("shared CSS remains the single owner of common card, field and action geometry", () => {
  assert.match(sharedCss, /\.operatorCard,[\s\S]*\.settingsCard,[\s\S]*\.diagnosticsTestCard\s*\{[\s\S]*border-radius:\s*10px/);
  assert.match(sharedCss, /\.operatorField,[\s\S]*\.settingsField,[\s\S]*\.diagnosticsField\s*\{[\s\S]*gap:\s*6px/);
  assert.match(sharedCss, /\.operatorButton,[\s\S]*\.settingsActions button,[\s\S]*\.loopbackExecutionActions button\s*\{[\s\S]*min-height:\s*38px/);
  assert.match(sharedCss, /\.ppuSiteCard/);
  assert.match(sharedCss, /\.ppuSiteButton/);
});
