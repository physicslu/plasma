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

test("uses the Plasma Web REST Gateway instead of browser-side job simulation", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.doesNotMatch(page, /setInterval\s*\(/);
  assert.match(page, /getPPUStatus/);
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

test("derives PPU identity and Site topology from canonical status instead of fixed eight-site assumptions", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.match(api, /export type PPUSnapshot/);
  assert.match(api, /export type SiteSnapshot/);
  assert.match(api, /export async function getPPUStatus/);
  assert.match(api, /payload\.ppu/);
  assert.match(api, /payload\.sites/);
  assert.match(api, /payload\.programmer/);
  assert.match(api, /payload\.channels/);
  assert.match(page, /useState<Site\[]>\(\[\]\)/);
  assert.match(page, /useState<PPUSnapshot \| null>\(null\)/);
  assert.match(page, /const status = await getPPUStatus\(apiBase\)/);
  assert.match(page, /status\.sites\.map/);
  assert.match(page, /current\.find\(site => site\.id === backend\.site_id\)/);
  assert.match(page, /sites\.find\(item => item\.id === siteId\)/);
  assert.match(page, /aria-label="PPU identity"/);
  assert.match(page, /ppu\.facility_id/);
  assert.match(page, /ppu\.ppu_id/);
  assert.match(page, /ppu\.model/);
  assert.ok(page.includes("{enabledCount}/{sites.length} Enabled"));
  assert.ok(page.includes("{visibleSiteIds.length} / {sites.length}"));
  assert.doesNotMatch(page, /Array\.from\(\{ length: 8 \}/);
  assert.doesNotMatch(page, /enabledCount\}\/8 Enabled/);
  assert.doesNotMatch(page, /visibleSiteIds\.length\} \/ 8/);
});

test("uses canonical Site requests while preserving the v3.1 channel compatibility field", async () => {
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.match(api, /siteId: number/);
  assert.match(api, /site_id: options\.siteId/);
  assert.match(api, /channel_id: options\.siteId/);
  assert.match(api, /const siteId = job\.site_id \?\? job\.channel_id/);
  assert.match(api, /Job snapshot is missing site_id/);
});

test("keeps live log messages English and marks error severity explicitly", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /type LogLevel = "info" \| "error"/);
  assert.match(page, /const logStageLabels: Record<Stage, string>/);
  assert.match(page, /const prefix = level === "error" \? "\[ERROR\] " : ""/);
  assert.match(page, /data-level=\{log\.level\}/);
  assert.match(page, /color: "var\(--red\)"/);
  assert.match(page, /Plasma Web REST Gateway offline/);
  assert.match(page, /offline · \$\{apiBase\} ·/);
  assert.match(page, /Plasma Web REST Gateway rejected · \$\{apiDraft\.trim\(\)/);
  assert.match(page, /Firmware exceeds the 16 MiB limit/);
  assert.match(page, /timed out waiting for completion/);
  assert.match(page, /At least one site must remain visible/);
  assert.doesNotMatch(page, /At least one channel must remain visible/);
  assert.doesNotMatch(page, /主畫面至少必須保留一個通道/);
  assert.doesNotMatch(page, /Firmware 超過 16 MiB 限制`/);
  assert.doesNotMatch(page, /等待完成逾時/);
  assert.doesNotMatch(page, /API URL 無效/);
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

test("executes browser API migration behavior for legacy, invalid, default, custom, and already-versioned values", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
  const defaultApiBase = api.match(
    /process\.env\.NEXT_PUBLIC_PLASMA_API_URL\s*\?\?\s*"([^"]+)"/,
  )?.[1];
  assert.ok(defaultApiBase, "Web fallback API URL is missing");
  const migration = extractTemplateLiteral(layout, "apiBaseStorageMigration", { DEFAULT_API_BASE: defaultApiBase });

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

  const savedDefault = runBrowserApiMigration(migration, {
    "plasma-api-base": defaultApiBase,
    "plasma-api-base-version": "2",
  });
  assert.equal(savedDefault["plasma-api-base"], undefined);
  assert.equal(savedDefault["plasma-api-base-version"], "2");

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

test("supports selected-site batch jobs and per-site controls", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /visibleSiteIds/);
  assert.match(page, /waitForTerminalJob/);
  assert.match(page, /terminalJobStates\.has\(current\.state\)/);
  assert.match(page, /const batchSiteIds = \[\.\.\.visibleSiteIds\]/);
  assert.match(page, /Promise\.all\(batchSiteIds\.map/);
  assert.match(page, /for \(const operation of batchOperations\)/);
  assert.match(page, /runSite\(siteId, operation, true, \(\) => lifecycle\.canDispatch\(siteId\)\)/);
  assert.match(page, /Batch stopped/);
  assert.match(page, /Batch complete/);
  assert.match(page, /runSite\(site\.id, operation\)/);
  assert.match(page, /At least one site must remain visible/);
  assert.match(page, /disabled=\{locked\}/);
  assert.match(page, /待命 <b>\{statusCounts\.idle\}/);
  assert.match(page, /工作中 <b>\{statusCounts\.busy\}/);
  assert.match(page, /成功 <b>\{statusCounts\.success\}/);
  assert.match(page, /取消 <b>\{statusCounts\.cancelled\}/);
  assert.match(page, /失敗 <b>\{statusCounts\.failed\}/);
  assert.match(page, /const disabledCount = sites\.length - enabledCount/);
  assert.match(page, /aria-label="Site 配置摘要"/);
  assert.ok(page.includes("顯示 <b>{visibleSiteIds.length} / {sites.length}</b>"));
  assert.match(page, /停用 <b>\{disabledCount\}<\/b>/);

  const batchStatus = page.match(
    /<div className="statusSummary" aria-label="選取 Site 狀態摘要">([\s\S]*?)<\/div>/,
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

test("uses an explicit batch lifecycle and a cancel barrier at dispatch", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const lifecycle = await readFile(new URL("../app/batch-lifecycle.ts", import.meta.url), "utf8");
  const api = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");

  assert.match(page, /const batchLifecycle = useRef<BatchLifecycle \| null>\(null\)/);
  assert.match(page, /const lifecycle = new BatchLifecycle\(batchSiteIds\)/);
  assert.match(lifecycle, /BatchCommandPhase = "ready" \| "submitting" \| "active" \| "terminal"/);
  assert.match(lifecycle, /beginSubmit\(siteId: number\)/);
  assert.match(lifecycle, /canDispatch\(siteId: number\)/);
  assert.match(lifecycle, /accepted\(siteId: number, jobId: string\)/);
  assert.match(lifecycle, /cancel\(\): BatchCancelSnapshot/);
  assert.match(page, /const \{ submittingSites, activeJobs \} = lifecycle\.cancel\(\)/);
  assert.match(page, /submitting: \$\{submittingSites\.length\} · active jobs: \$\{activeJobs\.length\}/);
  assert.match(page, /Promise\.all\(activeJobs\.map/);
  assert.doesNotMatch(page, /batchActiveJobs/);
  assert.doesNotMatch(page, /batchCancelRequested/);

  const encode = api.indexOf("await fileToBase64(options.firmware)");
  const guard = api.indexOf("if (options.submissionGuard && !options.submissionGuard())");
  const dispatch = api.indexOf('"/api/jobs"', guard);
  assert.notEqual(encode, -1, "firmware preparation is missing");
  assert.notEqual(guard, -1, "submission guard is missing");
  assert.notEqual(dispatch, -1, "job dispatch is missing");
  assert.ok(encode < guard, "cancel barrier must be checked after firmware preparation");
  assert.ok(guard < dispatch, "cancel barrier must be checked before POST /api/jobs");
});

test("keeps batch cancellation authoritative without rewriting the final job result", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /type BatchSiteState = "running" \| "cancelling" \| "success" \| "cancelled" \| "failed"/);
  assert.match(page, /batchSiteStates/);
  assert.match(page, /state === "running" \? "cancelling" : state/);
  assert.match(page, /批次取消中/);
  assert.match(page, /批次已取消/);
  assert.match(page, /批次進行中/);
  assert.match(page, /clearBatchSiteState\(siteId\)/);
  assert.match(page, /Job State/);
  assert.match(page, /Batch State/);
  assert.match(page, /Job State 保留 Python Job Manager 回傳的真實結果/);

  const cancellationPrecedence = page.indexOf(
    "const cancelWasRequested = lifecycle.cancelRequested || cancelRequests.current.has(job.job_id);",
  );
  const finalStateHandling = page.indexOf('if (finalJob.state === "cancelled")', cancellationPrecedence);
  const batchSuccess = page.indexOf('setBatchSiteState(siteId, "success")', cancellationPrecedence);
  assert.notEqual(cancellationPrecedence, -1, "batch cancellation precedence check is missing");
  assert.notEqual(finalStateHandling, -1, "final job state handling is missing");
  assert.notEqual(batchSuccess, -1, "batch success transition is missing");
  assert.ok(cancellationPrecedence < finalStateHandling, "cancel request must win before final job state classification");
  assert.ok(cancellationPrecedence < batchSuccess, "cancel request must win before batch success is published");

  const cancellingDisplay = page.indexOf('if (batchState === "cancelling")');
  const rawJobDisplay = page.indexOf("return { state: site.stage, label: stageLabels[site.stage] };");
  assert.notEqual(cancellingDisplay, -1, "batch cancelling display override is missing");
  assert.notEqual(rawJobDisplay, -1, "raw job display fallback is missing");
  assert.ok(cancellingDisplay < rawJobDisplay, "batch cancellation must override a racing job success in the Site UI");
});
