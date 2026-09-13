import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const consolePath = new URL("../app/fleet/factory-console-v2.tsx", import.meta.url);
const densityPath = new URL("../app/operator-ui/factory-live-density.css", import.meta.url);
const guidancePath = new URL("../app/operator-ui/production-workflow-guidance.css", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("PMode Live Site density keeps one eight-Site PPU readable and removes secondary detail only at higher density", async () => {
  const [consoleSource, density, guidance] = await Promise.all([
    source(consolePath),
    source(densityPath),
    source(guidancePath),
  ]);

  assert.match(consoleSource, /if \(siteCount <= 8\) return "spacious"/);
  assert.match(consoleSource, /if \(siteCount <= 20\) return "comfortable"/);
  assert.match(consoleSource, /if \(siteCount <= 40\) return "compact"/);
  assert.match(guidance, /@import "\.\/factory-live-density\.css"/);

  assert.match(density, /density-spacious[\s\S]*--site-card-w:\s*92px/);
  assert.match(density, /density-spacious[\s\S]*factorySiteLedCard > small[\s\S]*font-size:\s*8px/);
  assert.match(density, /density-compact[\s\S]*factorySiteLedCard > small,[\s\S]*density-dense[\s\S]*factorySiteLedCard > small[\s\S]*display:\s*none/);
  assert.match(density, /density-dense[\s\S]*--site-card-w:\s*60px/);

  for (const forbidden of [
    "createServerBatch",
    "cancelServerBatch",
    "getServerBatch",
    "evaluateBatchReadiness",
    "fetch(",
    "sessionStorage",
    "localStorage",
  ]) {
    assert.equal(density.includes(forbidden), false, `density policy must remain presentation-only: ${forbidden}`);
  }
});
