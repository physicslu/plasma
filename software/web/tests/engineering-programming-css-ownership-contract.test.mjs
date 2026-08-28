import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("Engineering shell and density layers do not own Programming controls", async () => {
  const [shell, density] = await Promise.all([
    source("../app/engineering/engineering.css"),
    source("../app/engineering/engineering-density.css"),
  ]);

  for (const selector of [
    ".engineeringGateway",
    ".engineeringBoundaryNote",
    ".engineeringOperationWarning",
    ".engineeringTargetSelector",
    ".engineeringTargetIdentity",
    ".simulationBadge",
    ".engineeringSelectorPanel",
    ".engineeringBatchPanel",
    ".engineeringBrowseButton",
    ".engineeringProgrammingHeader",
    ".compactFile",
  ]) {
    assert.doesNotMatch(shell, new RegExp(selector.replaceAll(".", "\\.")), `Engineering shell must not own ${selector}`);
    assert.doesNotMatch(density, new RegExp(selector.replaceAll(".", "\\.")), `Engineering density must not own ${selector}`);
  }

  assert.match(density, /\.engineeringShell\s*\{/);
  assert.match(density, /\.engineeringCanvas\.programmingActive\s*\{/);
});

test("Programming base owns chrome only and targeting field geometry has one owner", async () => {
  const [base, v2, refresh, readability, alignment] = await Promise.all([
    source("../app/engineering/programming-workspace-base.css"),
    source("../app/engineering/programming-workspace-v2.css"),
    source("../app/engineering/engineering-workspace-refresh.css"),
    source("../app/engineering/engineering-readability.css"),
    source("../app/engineering/engineering-alignment.css"),
  ]);

  assert.match(base, /\.productionProgrammingV2\s*\{/);
  assert.match(base, /\.productionProgrammingHeader\s*\{/);
  assert.doesNotMatch(base, /\.workflowField|\.topologyFoot|\.cardBody|\.productionProgrammingWorkflow|\.productionProgrammingRight|\.engineeringGateway/);

  assert.doesNotMatch(v2, /\.workflowField\s*\{/);
  assert.doesNotMatch(refresh, /\.workflowField\s*\{/);
  assert.match(alignment, /\.targetingCard \.workflowField\s*\{[\s\S]*display:\s*grid[\s\S]*align-items:\s*center[\s\S]*margin:\s*0/);
  assert.match(alignment, /@container engineering-programming \(min-width: 761px\)[\s\S]*grid-template-columns:\s*112px minmax\(0, 1fr\)[\s\S]*gap:\s*8px/);
  assert.match(alignment, /@container engineering-programming \(max-width: 760px\)[\s\S]*grid-template-columns:\s*1fr[\s\S]*gap:\s*12px/);
  assert.doesNotMatch(alignment, /@media \(max-width: 760px\)[\s\S]*\.targetingCard \.workflowField/);

  assert.match(readability, /\.workflowField,[\s\S]*\.workflowField select\s*\{\s*font-size:\s*11px/);
  assert.match(readability, /\.workflowField > span\s*\{\s*font-size:\s*12px[\s\S]*font-weight:\s*650/);
  assert.match(v2, /\.targetingCard \.workflowField select\s*\{[\s\S]*min-height:\s*var\(--operator-control-min-height\)[\s\S]*border:/);
});

test("EMode Programming-specific controls have one scoped presentation owner", async () => {
  const [workspace, shell, v2] = await Promise.all([
    source("../app/engineering/programming-workspace-v2.tsx"),
    source("../app/engineering/engineering.css"),
    source("../app/engineering/programming-workspace-v2.css"),
  ]);

  for (const liveClass of [
    "engineeringGateway",
    "engineeringBoundaryNote",
    "engineeringOperationWarning",
    "workflowField",
    "engineeringBatchSelectHead",
    "engineeringResult",
  ]) {
    assert.match(workspace, new RegExp(liveClass), `workspace must still render ${liveClass}`);
  }

  assert.match(v2, /\.engineeringProgrammingV2Header \.engineeringGateway\s*\{/);
  assert.match(v2, /\.engineeringProgrammingV2 \.engineeringBoundaryNote\s*\{/);
  assert.match(v2, /\.engineeringProgrammingV2 \.engineeringOperationWarning\s*\{/);
  assert.match(v2, /\.engineeringBatchSelectHead input,[\s\S]*\.engineeringBatchSelectCell input/);
  assert.doesNotMatch(shell, /\.engineeringGateway|\.engineeringBoundaryNote|\.engineeringOperationWarning/);
});

test("Engineering result colors consume Plasma semantic theme tokens", async () => {
  const v2 = await source("../app/engineering/programming-workspace-v2.css");

  assert.match(v2, /engineeringResult\[data-result="PASS"\][^\n]*var\(--green/);
  assert.match(v2, /engineeringResult\[data-result="FAIL"\],[\s\S]*engineeringResult\[data-result="ERROR"\][^\n]*var\(--red/);
  assert.match(v2, /engineeringResult\[data-result="CANCELLED"\],[\s\S]*engineeringResult\[data-result="STOPPED"\][^\n]*var\(--muted/);
  assert.doesNotMatch(v2, /engineeringResult[^\n]*color:\s*#[0-9a-f]{3,8}/i);
});

test("PMode LED Site cards and EMode diagnostic Site table remain intentional mode-specific surfaces", async () => {
  const [pmodCss, emodeCss] = await Promise.all([
    source("../app/fleet/factory-console-v2.css"),
    source("../app/engineering/programming-workspace-v2.css"),
  ]);

  assert.match(pmodCss, /\.factorySiteLedCard\s*\{/);
  assert.match(pmodCss, /--site-card-w:/);
  assert.match(emodeCss, /\.engineeringProgrammingV2 \.channelTable\s*\{/);
  assert.match(emodeCss, /\.engineeringBatchSelectHead/);
  assert.doesNotMatch(emodeCss, /\.factorySiteLed(?:Card|Grid)?\b/);
  assert.doesNotMatch(pmodCss, /\.engineeringBatchSelect(?:Head|Cell)\b/);
});
