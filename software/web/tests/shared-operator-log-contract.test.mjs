import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("PMode and EMode adapt domain logs into one OperatorLogPanel primitive", async () => {
  const [shared, production, engineering] = await Promise.all([
    source("../app/operator-ui/operator-log-panel.tsx"),
    source("../app/fleet/production-log-panel.tsx"),
    source("../app/engineering/engineering-log-panel.tsx"),
  ]);

  assert.match(shared, /export function OperatorLogPanel/);
  assert.match(shared, /import \{ OperatorPanelHeader \} from "\.\/operator-panel"/);
  assert.match(shared, /<OperatorPanelHeader title=\{title\} actions=\{actions\} \/>/);
  assert.match(shared, /className={`logCard operatorLogCard/);
  assert.match(shared, /className="operatorLogFilters"/);
  assert.match(shared, /import "\.\/operator-log-panel\.css"/);
  assert.match(shared, /filterItemAriaLabelPrefix/);
  assert.match(shared, /aria-label={`\$\{filterItemAriaLabelPrefix\} \$\{category\}`}/);
  assert.doesNotMatch(shared, /operatorLogHead|operatorLogTitle/);

  for (const adapter of [production, engineering]) {
    assert.match(adapter, /OperatorLogPanel/);
    assert.match(adapter, /OperatorLogEntry/);
    assert.doesNotMatch(adapter, /engineeringLogHead|engineeringLogFilters|engineeringLogTitle|engineeringLogActions/);
  }
  assert.match(production, /filterItemAriaLabelPrefix="Production log filter"/);
  assert.match(engineering, /filterItemAriaLabelPrefix="Engineering log filter"/);
  assert.doesNotMatch(production, /\.\.\/engineering\/engineering-log-panel/);
});

test("OperatorPanelHeader owns log title presentation while OperatorLogPanel owns log body presentation", async () => {
  const [sharedCss, panelCss] = await Promise.all([
    source("../app/operator-ui/operator-log-panel.css"),
    source("../app/operator-ui/operator-panel.css"),
  ]);

  for (const contract of [
    ".operatorLogCard {",
    "font-family: var(--font-sans), Arial, sans-serif;",
    ".operatorLogActions {",
    ".operatorLogFilters {",
    ".operatorLogCard pre {",
    'span[data-category="USR"]',
    'span[data-level="warn"]',
    'span[data-level="error"]',
    "@media (max-width: 760px)",
  ]) {
    assert.ok(sharedCss.includes(contract), `missing shared Operator Log contract: ${contract}`);
  }

  assert.doesNotMatch(sharedCss, /\.operatorLogHead|\.operatorLogTitle/);
  assert.match(panelCss, /\.operatorPanelHeader/);
  assert.match(panelCss, /\.operatorPanelTitle > span,[\s\S]*\.operatorPanelTitle > strong/);
});

test("mode-local Operator Log styles are placement-only and legacy style sheets are retired", async () => {
  const [productionPlacement, engineeringPlacement, engineeringPage] = await Promise.all([
    source("../app/fleet/production-log-placement.css"),
    source("../app/engineering/engineering-log-placement.css"),
    source("../app/engineering/page.tsx"),
  ]);

  for (const css of [productionPlacement, engineeringPlacement]) {
    assert.match(css, /margin-top:/);
    assert.doesNotMatch(css, /operatorPanelHeader|operatorPanelTitle|operatorLog(?:Head|Title|Actions|Filters)|operatorLogCard\s+pre|data-level|data-category/);
  }

  assert.doesNotMatch(engineeringPage, /engineering-log\.css/);
  await assert.rejects(fs.access(new URL("../app/engineering/engineering-log.css", import.meta.url)));
  await assert.rejects(fs.access(new URL("../app/fleet/production-log.css", import.meta.url)));
});
