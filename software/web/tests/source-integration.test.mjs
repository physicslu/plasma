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

function runBrowserApiMigration(script, initial, initialSession = {}) {
  const localStorage = createLocalStorage(initial);
  const sessionStorage = createLocalStorage(initialSession);
  runInNewContext(script, {
    URL,
    window: { localStorage, sessionStorage },
  });
  return { local: localStorage.snapshot(), session: sessionStorage.snapshot() };
}

test("uses canonical Web REST types and Site identity", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.match(api, /export type PPUSnapshot/);
  assert.match(api, /export type SiteSnapshot/);
  assert.match(api, /site_id: number/);
  // U10: plasma-api is a type module; the Browser has no direct Gateway client.
  assert.doesNotMatch(api, /fetch\(|\/api\/status|\/api\/jobs|\/api\/programming-assets/);
  assert.doesNotMatch(api, /channel_id/);
  assert.doesNotMatch(api, /payload\.programmer|payload\.channels/);
  assert.doesNotMatch(api, /LegacyChannel|LegacyProgrammer/);
});

test("EMode Programming owns single-PPU engineering operations through the Manager after legacy console retirement", async () => {
  const page = await readFile(new URL("../app/engineering/managed-programming-workspace.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/engineering/bundle-programming-api.ts", import.meta.url), "utf8");

  assert.match(api, /export const SEQUENCE_OPERATIONS = \["erase", "program", "verify"\] as const;/);
  assert.match(page, /aria-label=\{`Read SITE \$\{site\.site_id\} Flash`\}/);
  assert.match(page, /await runManagedRead\(\{ alias, siteId: id, icpn, address, length \}/);
  assert.equal((page.match(/runManagedBatch\(request, \{/g) ?? []).length, 1);
  assert.match(page, /await stopProgrammingBatch\(/);
  assert.doesNotMatch(page, /getEngineeringTargets|getPPUStatus|startJob|cancelJob|startEngineeringServerBatch|abortEngineeringServerBatch/);
  assert.doesNotMatch(page, /BatchLifecycle/);
});

test("uses same-origin as the default Browser route with no fixed remote Gateway", async () => {
  const workspace = await readFile(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  // Deployment API defaults are owned by the integration backend; the top-level
  // plasmactl script is now only the deployment-profile router.
  const plasmactlIntegration = await readFile(
    new URL("../../../utilities/plasmactl/backends/plasmactl-integration", import.meta.url),
    "utf8",
  );

  const deploymentDefault = plasmactlIntegration.match(
    /default_public_api_url="([^"]*)"/,
  )?.[1];

  assert.equal(deploymentDefault, "");
  // U10: the Browser route is always the same-origin Manager PPU prefix; no
  // build-time Gateway URL exists.
  assert.match(workspace, /return `\$\{window\.location\.origin\}\/api\/manager\/ppu`;/);
  assert.doesNotMatch(workspace + api, /NEXT_PUBLIC_PLASMA_API_URL/);
});

test("browser API storage v3 clears direct endpoints and wipes retired standalone routing and Batch keys", async () => {
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
    assert.equal(migrated.local["plasma-api-base"], undefined);
    assert.equal(migrated.local["plasma-api-base-version"], "3");
  }

  // U10: even after v3, the retired standalone mode and PPU-local Batch handles are wiped.
  const alreadyMigrated = runBrowserApiMigration(migration, {
    "plasma-api-base-version": "3",
    "plasma-api-mode": "standalone",
  }, {
    "plasma-production-active-batch-v1": "batch-p",
    "plasma-engineering-active-batch-v1": "batch-e",
    "plasma-managed-production-batch-v1": "manager-batch",
  });
  assert.equal(alreadyMigrated.local["plasma-api-mode"], undefined);
  assert.equal(alreadyMigrated.local["plasma-api-base-version"], "3");
  assert.equal(alreadyMigrated.session["plasma-production-active-batch-v1"], undefined);
  assert.equal(alreadyMigrated.session["plasma-engineering-active-batch-v1"], undefined);
  // The Manager Batch observation key is not a retired standalone handle.
  assert.equal(alreadyMigrated.session["plasma-managed-production-batch-v1"], "manager-batch");
});
