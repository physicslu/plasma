import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const settingsApi = await readFile(new URL("../app/gateway-settings-api.ts", import.meta.url), "utf8");
const settingsPanel = await readFile(new URL("../app/engineering/gateway-settings.tsx", import.meta.url), "utf8");
const sharedSettingsUi = await readFile(new URL("../app/operator-ui/settings-ui.tsx", import.meta.url), "utf8");
const sharedSettingsCss = await readFile(new URL("../app/operator-ui/settings-ui.css", import.meta.url), "utf8");
const sharedSurfaceCss = await readFile(new URL("../app/operator-ui/operator-surface-primitives.css", import.meta.url), "utf8");
const engineeringPage = await readFile(new URL("../app/engineering/page.tsx", import.meta.url), "utf8");
const engineeringCss = await readFile(new URL("../app/engineering/engineering.css", import.meta.url), "utf8");
const engineeringWorkspace = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");
const productionWorkspace = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const serverBatchApi = await readFile(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");
const serverBatchRuntime = await readFile(new URL("../../python/plasma_web/batch_runtime.py", import.meta.url), "utf8");

test("EMode Settings owns the server-backed shared Gateway communication policy", () => {
  assert.match(engineeringPage, /active === "settings"/);
  assert.match(engineeringPage, /type SettingsSection = "gateway" \| "mock"/);
  assert.match(engineeringPage, /selectSettingsSection\("gateway"\)/);
  assert.match(engineeringPage, /<GatewaySettingsPanel \/>/);
  assert.match(settingsApi, /\/api\/settings\/gateway/);
  assert.match(settingsApi, /ppu_request_timeout_ms: 10_000/);
  assert.match(settingsApi, /ppu_retry_count: 3/);
  assert.match(settingsPanel, /PPU Request Timeout seconds/);
  assert.match(settingsPanel, /PPU Retry Count/);
  assert.match(settingsPanel, /GATEWAY COMMUNICATION CONFIGURATION/);
  assert.match(settingsPanel, /Gateway 設定/);
  assert.match(settingsPanel, /<SettingsGrid columns=\{3\}>/);
  assert.doesNotMatch(settingsPanel, /<SettingsTabs/);
  assert.match(serverBatchApi, /gateway_settings\?: GatewaySettings/);
});

test("Gateway uses the shared Engineering Settings UI primitives without a redundant local tab shell", () => {
  for (const primitive of ["SettingsPage", "SettingsCard", "SettingsGrid", "SettingsField", "SettingsActions", "SettingsMessage", "SettingsGuide"]) {
    assert.match(settingsPanel, new RegExp(primitive));
    assert.match(sharedSettingsUi, new RegExp(`export function ${primitive}`));
  }
  assert.doesNotMatch(settingsPanel, /gateway-settings\.css/);
  assert.doesNotMatch(settingsPanel, /SettingsTabs/);
  assert.match(sharedSettingsCss, /@import "\.\/operator-surface-primitives\.css"/);
});

test("Shared Settings controls consume the Loopback-aligned operator surface geometry", () => {
  assert.match(sharedSurfaceCss, /min-height:\s*36px/);
  assert.match(sharedSurfaceCss, /border-radius:\s*6px/);
  assert.match(sharedSurfaceCss, /font:\s*11px var\(--font-mono\)/);
  assert.match(sharedSurfaceCss, /\.settingsActions button,[\s\S]*min-height:\s*38px/);
  assert.match(sharedSurfaceCss, /font:\s*700 11px\/1\.2 var\(--font-sans\)/);
  assert.doesNotMatch(sharedSettingsCss, /--settings-control-height|--settings-action-height/);
});

test("EMode settings children share one top-aligned Settings surface and keep Gateway help on the same page", () => {
  assert.match(engineeringPage, /settingsSurfaceActive = active === "settings"/);
  assert.match(engineeringPage, /settingsSection === "mock"/);
  assert.match(engineeringPage, /selectSettingsSection\("gateway"\)/);
  assert.match(engineeringPage, /selectSettingsSection\("mock"\)/);
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

test("Engineering direct Jobs use client Gateway policy while server Batch freezes authoritative Gateway policy", () => {
  assert.match(engineeringWorkspace, /configuredGatewayPolicy\.current = cachedGatewaySettings\(apiBase\)/);
  assert.match(engineeringWorkspace, /requestTimeoutMs:\s*configuredGatewayPolicy\.current\.ppu_request_timeout_ms/);
  assert.match(engineeringWorkspace, /const policy = configuredGatewayPolicy\.current/);
  assert.match(engineeringWorkspace, /withCommunicationRetry/);
  assert.match(engineeringWorkspace, /getGatewayLiveness/);
  assert.match(engineeringWorkspace, /GatewayUnavailableError/);
  assert.match(engineeringWorkspace, /Server Batch Runtime freezes its own authoritative Gateway policy at START/);
  assert.match(plasmaApi, /inFlightJobSnapshots/);
  assert.match(plasmaApi, /readonly transient = false/);

  assert.match(serverBatchRuntime, /gateway_policy=self\.gateway_settings\.snapshot\(\)/);
  assert.match(serverBatchRuntime, /retries = batch\.gateway_policy\.ppu_retry_count if retryable else 0/);
  assert.match(serverBatchRuntime, /timeout=batch\.gateway_policy\.request_timeout_s/);
  assert.match(serverBatchRuntime, /batch\.failed_ppus\.add\(ppu_key\)/);
  assert.match(serverBatchRuntime, /_cancel_active_jobs\(batch, ppu_key=ppu_key\)/);
});

test("manufacturing Yield is undefined until an IC has a PASS or FAIL outcome", () => {
  assert.match(engineeringWorkspace, /const yieldLabel = completedIc > 0/);
  assert.match(engineeringWorkspace, /:\s*"—"/);
  assert.match(productionWorkspace, /manufacturing\.total > 0 \? .* : "—"/);
  assert.match(productionWorkspace, /communicationState === "reconnecting"/);
});
