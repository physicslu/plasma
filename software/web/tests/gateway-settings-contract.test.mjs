import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const settingsApi = await readFile(new URL("../app/gateway-settings-api.ts", import.meta.url), "utf8");
const settingsPanel = await readFile(new URL("../app/engineering/gateway-settings.tsx", import.meta.url), "utf8");
const sharedSettingsUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const sharedSettingsCss = await readFile(new URL("../app/operator-ui/settings-ui.css", import.meta.url), "utf8");
const engineeringPage = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const engineeringCss = await readFile(new URL("../app/engineering/engineering.css", import.meta.url), "utf8");
const engineeringWorkspace = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const productionWorkspace = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const serverBatchApi = await readFile(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");

test("EMode Settings owns the server-backed shared Gateway communication policy", () => {
  assert.match(engineeringPage, /active === "settings"/);
  assert.match(engineeringPage, /<GatewaySettingsPanel \/>/);
  assert.match(settingsApi, /\/api\/settings\/gateway/);
  assert.match(settingsApi, /ppu_request_timeout_ms: 10_000/);
  assert.match(settingsApi, /ppu_retry_count: 3/);
  assert.match(settingsPanel, /PPU Request Timeout seconds/);
  assert.match(settingsPanel, /PPU Retry Count/);
  assert.match(settingsPanel, /<SettingsTabs ariaLabel="Engineering settings categories">/);
  assert.match(settingsPanel, /aria-current="page">Gateway<\/button>/);
  assert.match(serverBatchApi, /gateway_settings\?: GatewaySettings/);
});

test("Gateway uses the shared Engineering Settings UI primitives", () => {
  for (const primitive of ["SettingsPage", "SettingsTabs", "SettingsCard", "SettingsGrid", "SettingsField", "SettingsActions", "SettingsMessage", "SettingsGuide"]) {
    assert.match(settingsPanel, new RegExp(primitive));
    assert.match(sharedSettingsUi, new RegExp(`export function ${primitive}`));
  }
  assert.doesNotMatch(settingsPanel, /gateway-settings\.css/);
});

test("EMode settings surfaces stay top-aligned and keep Gateway help on the same page", () => {
  assert.match(engineeringPage, /settingsSurfaceActive = active === "settings" \|\| active === "mock"/);
  assert.match(engineeringPage, /settingsSurfaceActive \? "settingsActive"/);
  assert.match(engineeringCss, /\.engineeringCanvas\.settingsActive\s*\{[\s\S]*?place-items:\s*start stretch;/);
  assert.match(settingsPanel, /ariaLabel="Gateway Settings Guide"/);
  assert.match(settingsPanel, /Gateway 設定說明/);
  assert.match(settingsPanel, /測試方法/);
  assert.match(settingsPanel, /Mock 的 E\/P\/V\/R Error Rate/);
});

test("Shared Settings Guide renders explicit full-width-colon step numbers", () => {
  assert.match(sharedSettingsCss, /counter-reset:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /counter-increment:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /content:\s*counter\(settings-test-step\)\s*"："/);
  assert.match(sharedSettingsCss, /list-style:\s*none/);
});

test("Engineering freezes communication policy and reconciles only accepted PPU Jobs", () => {
  assert.match(engineeringWorkspace, /const gatewayPolicy = \{ \.\.\.configuredGatewayPolicy\.current \}/);
  assert.match(engineeringWorkspace, /withCommunicationRetry/);
  assert.match(engineeringWorkspace, /getGatewayLiveness/);
  assert.match(engineeringWorkspace, /GatewayUnavailableError/);
  assert.match(engineeringWorkspace, /isolateFailedPpu/);
  assert.match(engineeringWorkspace, /CANCEL RECONCILIATION PENDING/);
  assert.match(plasmaApi, /inFlightJobSnapshots/);
  assert.match(plasmaApi, /readonly transient = false/);
});

test("manufacturing Yield is undefined until an IC has a PASS or FAIL outcome", () => {
  assert.match(engineeringWorkspace, /const yieldLabel = completedIc > 0/);
  assert.match(engineeringWorkspace, /:\s*"—"/);
  assert.match(productionWorkspace, /manufacturing\.total > 0 \? .* : "—"/);
  assert.match(productionWorkspace, /communicationState === "reconnecting"/);
});
