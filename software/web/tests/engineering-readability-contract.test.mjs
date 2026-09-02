import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readabilityPath = new URL("../app/engineering/engineering-readability.css", import.meta.url);
const refreshPath = new URL("../app/engineering/engineering-workspace-refresh.css", import.meta.url);
const sharedControlsPath = new URL("../app/operator-ui/programming-job-controls.css", import.meta.url);
const designContractPath = new URL("../app/operator-ui/operator-design-contract.css", import.meta.url);
const panelCssPath = new URL("../app/operator-ui/operator-panel.css", import.meta.url);
const operatorSurfacePrimitivesPath = new URL("../app/operator-ui/operator-surface-primitives.css", import.meta.url);
const ppuSiteCssPath = new URL("../app/engineering/ppu-site-configuration.css", import.meta.url);
const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering readability owns only Engineering targeting and live Site body typography", async () => {
  const [css, sharedControls, designContract] = await Promise.all([
    source(readabilityPath),
    source(sharedControlsPath),
    source(designContractPath),
  ]);

  for (const contract of [
    ".workflowField,\n.engineeringProgrammingV2 .workflowField select {\n  font-size: 11px;",
    ".workflowField > span {\n  font-size: 12px;",
    ".topologyFoot {\n  font-size: 10px;",
    ".channelTable {\n  font-size: 12px;",
    ".channelTable th {\n  font-size: 10px;",
    ".channelTable td:nth-child(2) b {\n  font-size: 13px;",
    ".channelTable .state {\n  font-size: 10px;",
  ]) {
    assert.ok(css.includes(contract), `missing readability contract: ${contract}`);
  }

  for (const forbidden of [
    ".programmingJob",
    ".jobRow",
    ".imageField",
    ".engineeringBrowseButton",
    ".engineeringImageHint",
    ".engineeringPolicyRow",
    ".engineeringRetryField",
    ".programmingBatchOperations",
    ".batchReadiness {",
    ".programmingActions button",
    ".targetingCard > header",
    ".liveSiteStatus > header",
    "::before",
  ]) {
    assert.equal(css.includes(forbidden), false, `Engineering readability must not own shared/header selector: ${forbidden}`);
  }

  assert.match(sharedControls, /\.programmingJobOperationChecks label\s*\{[\s\S]*font-size:\s*var\(--operator-control-font-size\)[\s\S]*font-weight:\s*550/);
  assert.match(sharedControls, /\.programmingJobStart,[\s\S]*\.programmingJobAbort\s*\{[\s\S]*font-size:\s*var\(--operator-action-font-size\)[\s\S]*font-weight:\s*800/);
  assert.match(designContract, /--operator-control-font-size:\s*10px/);
  assert.match(designContract, /--operator-action-font-size:\s*11px/);
  assert.doesNotMatch(
    css,
    /operatorKpiStrip|batchSummary(?:Header|Grid)|data-kpi=/,
    "Batch Summary typography must stay with the shared component",
  );
});

test("Engineering numbering is metadata only and shared Operator Panel owns first-level title presentation", async () => {
  const [css, refresh, panelCss] = await Promise.all([
    source(readabilityPath),
    source(refreshPath),
    source(panelCssPath),
  ]);

  assert.match(refresh, /\.engineeringProgrammingV2 \.targetingCard > header::before\s*\{\s*content:\s*"1\. ";/);
  assert.match(refresh, /\.engineeringProgrammingV2 \.liveSiteStatus > header > span::before\s*\{\s*content:\s*"3\. ";/);
  assert.doesNotMatch(refresh, /font-size:\s*0/);
  assert.doesNotMatch(refresh, /content:\s*"1\. SYSTEM SETUP|content:\s*"3\. LIVE SITE STATUS/);
  assert.match(panelCss, /\.operatorPanelHeader,[\s\S]*\.productionProgrammingCard > header/);
  assert.match(panelCss, /font-size:\s*var\(--operator-panel-title-font-size\)/);
  assert.match(panelCss, /font-weight:\s*900/);
  assert.doesNotMatch(css, /targetingCard > header|liveSiteStatus > header/);
  assert.doesNotMatch(
    `${css}\n${refresh}`,
    /\.programmingJob(?:Panel|Card|Grid|Field|ActionBar|Status|OperationChecks|PolicyControls)\b/,
    "Engineering styles must not own shared Programming Job presentation",
  );
});

test("Engineering readability layer is typography-only and loads after layout CSS", async () => {
  const [css, page] = await Promise.all([source(readabilityPath), source(pagePath)]);

  for (const forbidden of [
    "grid-template",
    "grid-column",
    "grid-row",
    "display:",
    "width:",
    "height:",
    "padding:",
    "margin:",
    "gap:",
    "position:",
  ]) {
    assert.equal(css.includes(forbidden), false, `readability layer must not own layout property ${forbidden}`);
  }

  const refresh = page.indexOf('import "./engineering-workspace-refresh.css";');
  const readability = page.indexOf('import "./engineering-readability.css";');
  assert.ok(refresh >= 0 && readability > refresh, "readability CSS must load after the approved Engineering layout CSS");
});

test("PPU Site management consumes canonical Settings/Loopback operator primitives and stays single-column", async () => {
  const [ppuCss, primitives] = await Promise.all([
    source(ppuSiteCssPath),
    source(operatorSurfacePrimitivesPath),
  ]);

  assert.match(
    ppuCss,
    /^@import "\.\.\/operator-ui\/operator-surface-primitives\.css";/m,
    "PPU/Site management must consume the canonical Settings/Loopback operator surface owner",
  );

  assert.match(primitives, /\.settingsCard,\s*\.diagnosticsTestCard,\s*\.ppuSiteCard\s*\{/);
  assert.match(primitives, /\.settingsActions button,\s*\.loopbackExecutionActions button,\s*\.ppuSiteButton\s*\{/);
  assert.match(primitives, /\.ppuRegistryAddForm input\s*\{/);

  assert.doesNotMatch(ppuCss, /^\.ppuSiteCard\s*\{/m, "PPU cards must not redeclare the shared card primitive");
  assert.doesNotMatch(ppuCss, /^\.ppuSiteButton\s*\{/m, "PPU actions must not redeclare the shared action primitive");
  assert.doesNotMatch(ppuCss, /^\.ppuRegistryAddForm input\s*\{/m, "PPU fields must not redeclare the shared input primitive");

  assert.match(ppuCss, /\.ppuSiteLayout\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(ppuCss, /\.ppuSiteColumn\s*\{[\s\S]*display:\s*contents/);
  assert.match(ppuCss, /first-child > \.ppuSiteCard:first-child \{ order: 1; \}/);
  assert.match(ppuCss, /nth-child\(2\) > \.ppuSiteCard:first-child \{ order: 2; \}/);
  assert.match(ppuCss, /nth-child\(2\) > \.ppuSiteCard:nth-child\(2\) \{ order: 3; \}/);
});
