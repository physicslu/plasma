import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

function extractTemplateLiteral(source, constantName) {
  const marker = `const ${constantName} = \``;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `${constantName} template literal is missing`);
  const contentStart = start + marker.length;
  const end = source.indexOf("`;", contentStart);
  assert.notEqual(end, -1, `${constantName} template literal is unterminated`);
  const literalSource = source.slice(contentStart, end);
  return runInNewContext(`\`${literalSource}\``);
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

test("uses the Python Gateway API instead of browser-side job simulation", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.doesNotMatch(page, /setInterval\s*\(/);
  assert.match(page, /getChannels/);
  assert.match(page, /getJob/);
  assert.match(page, /startJob/);
  assert.match(page, /cancelJob/);
  assert.match(page, /REST → Plasma v3\.1 TCP/);
  assert.match(api, /\/api\/status/);
  assert.match(api, /\/api\/jobs/);
  assert.match(api, /await fetch/);
  assert.match(api, /process\.env\.NEXT_PUBLIC_PLASMA_API_URL\s*\?\?/);
  assert.doesNotMatch(api, /127\.0\.0\.1:8080/);
});

test("keeps the Web fallback aligned with the deployment default without fixing the endpoint in tests", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  const plasmactl = await readFile(new URL("../../../scripts/plasmactl", import.meta.url), "utf8");

  const webDefault = api.match(
    /process\.env\.NEXT_PUBLIC_PLASMA_API_URL\s*\?\?\s*"([^"]+)"/,
  )?.[1];
  const deploymentDefault = plasmactl.match(
    /default_public_api_url="([^"]+)"/,
  )?.[1];

  assert.ok(webDefault, "Web fallback API URL is missing");
  assert.ok(deploymentDefault, "deployment default API URL is missing");
  assert.match(webDefault, /^https?:\/\//);
  assert.equal(webDefault, deploymentDefault);
});

test("executes browser API migration behavior for legacy, invalid, custom, and already-versioned values", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const migration = extractTemplateLiteral(layout, "apiBaseStorageMigration");

  for (const legacyApiBase of [
    "https://swpc.tail820e64.ts.net",
    "https://swpc.tail820e64.ts.net:8443",
    "http://127.0.0.1:8080",
  ]) {
    const migrated = runBrowserApiMigration(migration, {
      "plasma-api-base": legacyApiBase,
    });
    assert.equal(migrated["plasma-api-base"], undefined);
    assert.equal(migrated["plasma-api-base-version"], "2");
  }

  const invalid = runBrowserApiMigration(migration, {
    "plasma-api-base": "not a URL",
  });
  assert.equal(invalid["plasma-api-base"], undefined);
  assert.equal(invalid["plasma-api-base-version"], "2");

  const customApiBase = "https://programmer.customer.example.invalid";
  const custom = runBrowserApiMigration(migration, {
    "plasma-api-base": customApiBase,
  });
  assert.equal(custom["plasma-api-base"], customApiBase);
  assert.equal(custom["plasma-api-base-version"], "2");

  const explicitVersionedLegacy = runBrowserApiMigration(migration, {
    "plasma-api-base": "https://swpc.tail820e64.ts.net:8443",
    "plasma-api-base-version": "2",
  });
  assert.equal(
    explicitVersionedLegacy["plasma-api-base"],
    "https://swpc.tail820e64.ts.net:8443",
  );
  assert.equal(explicitVersionedLegacy["plasma-api-base-version"], "2");
});

test("supports selected-channel batch jobs and per-channel controls", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /visibleChannelIds/);
  assert.match(page, /waitForTerminalJob/);
  assert.match(page, /terminalJobStates\.has\(current\.state\)/);
  assert.match(page, /const batchChannelIds = \[\.\.\.visibleChannelIds\]/);
  assert.match(page, /Promise\.all\(batchChannelIds\.map/);
  assert.match(page, /for \(const operation of batchOperations\)/);
  assert.match(page, /runChannel\(channelId, operation, true\)/);
  assert.match(page, /Batch stopped/);
  assert.match(page, /Batch complete/);
  assert.match(page, /runChannel\(channel\.id, operation\)/);
  assert.match(page, /主畫面至少必須保留一個通道/);
  assert.match(page, /disabled=\{locked\}/);
  assert.match(page, /待命 <b>\{statusCounts\.idle\}/);
  assert.match(page, /工作中 <b>\{statusCounts\.busy\}/);
  assert.match(page, /成功 <b>\{statusCounts\.success\}/);
  assert.match(page, /失敗 <b>\{statusCounts\.failed\}/);
  assert.match(page, /const disabledCount = channels\.length - enabledCount/);
  assert.match(page, /aria-label="通道配置摘要"/);
  assert.match(page, /顯示 <b>\{visibleChannelIds\.length\} \/ 8<\/b>/);
  assert.match(page, /停用 <b>\{disabledCount\}<\/b>/);

  const batchStatus = page.match(
    /<div className="statusSummary" aria-label="選取通道狀態摘要">([\s\S]*?)<\/div>/,
  )?.[1];
  assert.ok(batchStatus, "batch status summary is missing");
  assert.doesNotMatch(batchStatus, /停用/);

  assert.match(page, /useState<Operation\[]>\(\[\]\)/);
  assert.doesNotMatch(page, /批次操作至少必須選擇一項/);
  assert.match(page, /aria-label=\{`批次操作：\$\{operationLabels\[operation\]\}`\}/);
  assert.match(page, /type="checkbox"/);
  assert.match(page, /selectedBatchOperations\.length === 0/);
  assert.match(page, /批次執行：尚未選擇操作/);
  assert.match(page, /runBatch\(selectedBatchOperations\)/);
  assert.match(page, /批次執行/);
});

test("cancels active batch jobs without coupling channel pipelines", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /const batchCancelRequested = useRef\(false\)/);
  assert.match(page, /const batchActiveJobs = useRef<Record<number, string>>\(\{\}\)/);
  assert.match(page, /async function cancelBatch\(\)/);
  assert.match(page, /batchCancelRequested\.current = true/);
  assert.match(page, /Object\.entries\(batchActiveJobs\.current\)/);
  assert.match(page, /Promise\.all\(activeJobs\.map/);
  assert.match(page, /requestJobCancel\(Number\(channelId\), jobId, true\)/);
  assert.match(page, /if \(batchCancelRequested\.current\)/);
  assert.match(page, /delete batchActiveJobs\.current\[channelId\]/);
  assert.match(page, /className="cancelBatch"/);
  assert.match(page, /aria-label="取消批次工作"/);
  assert.match(page, /取消批次/);
});
