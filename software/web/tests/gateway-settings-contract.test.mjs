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
const engineeringWorkspace = await readFile(new URL("../app/engineering/managed-programming-workspace.tsx", import.meta.url), "utf8");
const batchStatistics = await readFile(new URL("../app/programming/batch-statistics.ts", import.meta.url), "utf8");
const productionWorkspace = await readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
const gatewayModule = await readFile(new URL("../../python/plasma_web/gateway.py", import.meta.url), "utf8");
const retiredBatchRuntime = new URL("../../python/plasma_web/batch_runtime.py", import.meta.url);

test("EMode Settings owns the server-backed shared Plasma Gateway communication policy", () => {
  assert.match(engineeringPage, /active === "settings"/);
  assert.match(engineeringPage, /type SettingsSection = "gateway" \| "mock"/);
  assert.match(engineeringPage, /selectSettingsSection\("gateway"\)/);
  assert.match(engineeringPage, /<span className="engineeringNavLabel">Plasma Gateway<\/span>/);
  assert.match(engineeringPage, /<GatewaySettingsPanel \/>/);
  assert.match(settingsApi, /\/api\/settings\/gateway/);
  assert.match(settingsApi, /ppu_request_timeout_ms: number/);
  assert.match(settingsApi, /ppu_retry_count: number/);
  assert.match(settingsPanel, /PPU Request Timeout seconds/);
  assert.match(settingsPanel, /PPU Retry Count/);
  assert.match(settingsPanel, /PLASMA GATEWAY COMMUNICATION CONFIGURATION/);
  assert.match(settingsPanel, /Plasma Gateway 設定/);
  assert.match(settingsPanel, /Plasma Gateway Settings/);
  assert.match(settingsPanel, /<SettingsGrid columns=\{3\}>/);
  assert.doesNotMatch(settingsPanel, /<SettingsTabs/);
});

test("Plasma Gateway settings retain compatibility-sensitive internal identifiers", () => {
  assert.match(settingsApi, /\/api\/settings\/gateway/);
  assert.match(engineeringPage, /type SettingsSection = "gateway" \| "mock"/);
  assert.match(engineeringPage, /selectSettingsSection\("gateway"\)/);
  assert.match(settingsPanel, /getGatewaySettings/);
  assert.match(settingsPanel, /updateGatewaySettings/);
});

test("Plasma Gateway uses the shared Engineering Settings UI primitives without a redundant local tab shell", () => {
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

test("EMode settings children share one top-aligned Settings surface and keep Plasma Gateway help on the same page", () => {
  assert.match(engineeringPage, /settingsSurfaceActive = active === "settings"/);
  assert.match(engineeringPage, /settingsSection === "mock"/);
  assert.match(engineeringPage, /selectSettingsSection\("gateway"\)/);
  assert.match(engineeringPage, /selectSettingsSection\("mock"\)/);
  assert.match(engineeringPage, /settingsSurfaceActive \? "settingsActive"/);
  assert.match(engineeringCss, /\.engineeringCanvas\.settingsActive\s*\{[\s\S]*?place-items:\s*start stretch;/);
  assert.match(settingsPanel, /ariaLabel="Plasma Gateway Settings Guide"/);
  assert.match(settingsPanel, /Plasma Gateway 設定說明/);
  assert.match(settingsPanel, /測試方法/);
  assert.match(settingsPanel, /Mock 的 E\/P\/V\/R Error Rate/);
});

test("Shared Settings Guide renders explicit full-width-colon step numbers", () => {
  assert.match(sharedSettingsCss, /counter-reset:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /counter-increment:\s*settings-test-step/);
  assert.match(sharedSettingsCss, /content:\s*counter\(settings-test-step\)\s*"："/);
  assert.match(sharedSettingsCss, /list-style:\s*none/);
});

test("the PPU runs no Batch: Gateway policy is not frozen into a PPU-local Batch (U10)", async () => {
  // The Console issues no direct Jobs or PPU-local Batches, and the PPU-local
  // Batch runtime is retired: every Batch is Manager-owned.
  assert.doesNotMatch(engineeringWorkspace, /cachedGatewaySettings|getGatewayLiveness|withCommunicationRetry|gateway-settings-api/);
  await assert.rejects(readFile(retiredBatchRuntime, "utf8"), { code: "ENOENT" });
  assert.match(gatewayModule, /PPU_BATCH_RETIRED/);
  assert.doesNotMatch(gatewayModule, /batch_runtime|BatchRuntimeManager/);
});

test("manufacturing Yield is undefined until an IC has a PASS or FAIL outcome", () => {
  // EMode and PMode share Batch Statistics v1: YIELD is N/A until a Cycle settles.
  assert.match(batchStatistics, /return settled > 0 \? `\$\{\(\(pass \/ settled\) \* 100\)\.toFixed\(1\)\}%` : "N\/A";/);
  assert.match(engineeringWorkspace, /const kpis = statisticsKpis\(statistics, formatElapsed\(elapsed\)\);/);
  // PMode (Batch Statistics v1): N/A without a settled Cycle, never 100%.
  assert.match(productionWorkspace, /statisticsKpis\(statistics,/);
  assert.match(productionWorkspace, /communicationState === "reconnecting"/);
});
