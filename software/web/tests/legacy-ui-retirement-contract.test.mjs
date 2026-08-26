import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const retiredPaths = [
  "../app/batch-dashboard-panels.tsx",
  "../app/batch-dashboard-panels.css",
  "../app/programming-batch-toolbar.css",
  "../app/fleet/server-batch-page.tsx",
  "../app/fleet/server-batch.css",
  "../app/fleet/fps-selector-layout.css",
  "../app/fleet/fleet.css",
  "../app/fleet/operator-feedback.css",
  "../app/fleet/production-prototype.css",
  "../app/fleet/pmod-theme.css",
  "../app/engineering/programming-workspace.tsx",
  "../../../.github/workflows/pr99-format-cleanup.yml",
  "../../../.github/workflows/unified-pe-dashboard-verify.yml",
];

async function source(path) {
  return await fs.readFile(new URL(path, import.meta.url), "utf8");
}

test("retired Production and Engineering Batch surfaces stay absent", async () => {
  for (const path of retiredPaths) {
    await assert.rejects(
      fs.access(new URL(path, import.meta.url)),
      error => Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT"),
      `${path} must remain retired`,
    );
  }
});

test("active routes point only at Factory Console v2 and Programming Workspace v2", async () => {
  const fleetPage = await source("../app/fleet/page.tsx");
  const engineeringPage = await source("../app/engineering/page.tsx");
  const globalNav = await source("../app/global-nav.tsx");

  assert.match(fleetPage, /FactoryConsoleV2/);
  assert.match(engineeringPage, /ProgrammingWorkspaceV2/);
  assert.doesNotMatch(engineeringPage, /ProgrammingWorkspace(?!V2)/);
  assert.doesNotMatch(globalNav, /pmod-theme\.css/);
});
