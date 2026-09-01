import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

function extractTemplateLiteral(source, constantName, context = {}) {
  const marker = `const ${constantName} = \``;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `${constantName} template literal is missing`);
  const contentStart = start + marker.length;
  const end = source.indexOf("`;", contentStart);
  assert.notEqual(end, -1, `${constantName} template literal is unterminated`);
  const literalSource = source.slice(contentStart, end);
  return runInNewContext(`\`${literalSource}\``, context);
}

function createLocalStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
    snapshot() {
      return Object.fromEntries(values);
    },
  };
}

function runBrowserApiMigration(script, initial) {
  const localStorage = createLocalStorage(initial);
  runInNewContext(script, {
    URL,
    window: { localStorage },
  });
  return localStorage.snapshot();
}

test("uses canonical Web REST APIs and Site identity", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.match(api, /export type PPUSnapshot/);
  assert.match(api, /export type SiteSnapshot/);
  assert.match(api, /export async function getPPUStatus/);
  assert.match(api, /payload\.ppu/);
  assert.match(api, /payload\.sites/);
  assert.match(api, /siteId: number/);
  assert.match(api, /site_id: options\.siteId/);
  assert.match(api, /\/api\/status/);
  assert.match(api, /\/api\/jobs/);
  assert.match(api, /\/api\/programming-assets/);
  assert.match(api, /await fetch/);
  assert.doesNotMatch(api, /channel_id/);
  assert.doesNotMatch(api, /payload\.programmer|payload\.channels/);
  assert.doesNotMatch(api, /LegacyChannel|LegacyProgrammer/);
  assert.match(api, /Job snapshot is missing a valid site_id/);
});

test("EMode Programming owns single-PPU engineering operations after legacy console retirement", async () => {
  const page = await readFile(new URL("../app/engineering/programming-workspace-v2.tsx", import.meta.url), "utf8");

  assert.match(page, /getEngineeringTargets/);
  assert.match(page, /getPPUStatus/);
  assert.match(page, /startJob/);
  assert.match(page, /cancelJob/);
  assert.match(page, /operationOrder: Operation\[] = \["erase", "program", "verify", "read"\]/);
  assert.match(page, /runSingleSite\(site\.id, operation\)/);
  assert.match(page, /readDownloadUrl\(targetApiBase, site\.jobId, site\.outputFile\)/);
  assert.match(page, /startEngineeringServerBatch/);
  assert.match(page, /abortEngineeringServerBatch/);
  assert.match(page, /executionPolicy:/);
  assert.match(page, /site_retry_limit:/);
  assert.doesNotMatch(page, /BatchLifecycle/);
  assert.doesNotMatch(page, /new BatchLifecycle/);
});

test("uses same-origin as the default Browser route with no fixed remote Gateway", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  const plasmactl = await readFile(new URL("../../../scripts/plasmactl", import.meta.url), "utf8");

  const webDefault = api.match(
    /process\.env\.NEXT_PUBLIC_PLASMA_API_URL\s*\?\?\s*"([^"]*)"/,
  )?.[1];
  const deploymentDefault = plasmactl.match(
    /default_public_api_url="([^"]*)"/,
  )?.[1];

  assert.equal(webDefault, "");
  assert.equal(deploymentDefault, "");
  assert.match(api, /if \(!trimmed\) return ""/);
  assert.doesNotMatch(api, /process\.env\.NEXT_PUBLIC_PLASMA_API_URL\s*\?\?\s*"https?:\/\//);
});

test("browser API storage v3 clears pre-v3 direct endpoints while preserving only post-migration explicit standalone input", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const migration = extractTemplateLiteral(layout, "apiBaseStorageMigration");

  for (const priorValue of [
    "https://legacy-gateway.invalid",
    "http://127.0.0.1:8080",
    "not a URL",
    "https://programmer.customer.example.invalid",
  ]) {
    const migrated = runBrowserApiMigration(migration, {
      "plasma-api-base": priorValue,
      "plasma-api-base-version": "2",
    });
    assert.equal(migrated["plasma-api-base"], undefined);
    assert.equal(migrated["plasma-api-base-version"], "3");
  }

  const alreadyMigrated = runBrowserApiMigration(migration, {
    "plasma-api-base": "https://engineering-standalone.example.invalid",
    "plasma-api-base-version": "3",
  });
  assert.equal(alreadyMigrated["plasma-api-base"], "https://engineering-standalone.example.invalid");
  assert.equal(alreadyMigrated["plasma-api-base-version"], "3");
});
