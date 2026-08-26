import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function workerFor(name) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${name}-${process.pid}-${Date.now()}`);
  return (await import(workerUrl.href)).default;
}

const env = { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } };
const ctx = { waitUntil() {}, passThroughOnException() {} };

test("public Plasma host sends root users to the product-mode landing page", async () => {
  const worker = await workerFor("demo-root");
  const response = await worker.fetch(new Request("https://plasma.open4th.com/", { headers: { accept: "text/html" }, redirect: "manual" }), env, ctx);
  assert.ok([301, 302, 307, 308].includes(response.status));
  assert.equal(new URL(response.headers.get("location"), "https://plasma.open4th.com").pathname, "/demo");
});

test("non-public local root keeps the original PPU console behavior", async () => {
  const worker = await workerFor("local-root");
  const response = await worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), env, ctx);
  assert.equal(response.status, 200);
  assert.match(await response.text(), />SITE MATRIX</);
});

test("demo landing page exposes Production and Engineering as the only product modes", async () => {
  const worker = await workerFor("demo-page");
  const response = await worker.fetch(new Request("http://localhost/demo", { headers: { accept: "text/html" } }), env, ctx);
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, />選擇產品模式</);
  assert.match(html, /href="\/fleet"/);
  assert.match(html, />量產模式</);
  assert.match(html, /href="\/engineering"/);
  assert.match(html, />工程模式</);
  assert.doesNotMatch(html, />Single PPU Demo</);
  assert.doesNotMatch(html, />Manager \/ Fleet Demo</);
});

test("Web source defines ProductMode rather than Fleet as a product-mode value", async () => {
  const model = await fs.readFile(new URL("../app/product-mode.ts", import.meta.url), "utf8");
  const nav = await fs.readFile(new URL("../app/global-nav.tsx", import.meta.url), "utf8");
  assert.match(model, /ProductMode\s*=\s*"production"\s*\|\s*"engineering"/);
  assert.match(model, /production:\s*"\/fleet"/);
  assert.match(model, /engineering:\s*"\/engineering"/);
  assert.match(nav, /PRODUCT_MODE_ROUTES\.production/);
  assert.match(nav, /PRODUCT_MODE_ROUTES\.engineering/);
  assert.match(nav, /getBatchExecutionActivityCount/);
  assert.match(nav, /subscribeBatchExecutionActivity/);
  assert.doesNotMatch(nav, /nav\.fleet/);
  assert.doesNotMatch(nav, /nav\.singlePpu/);
});

test("Factory Console v2 separates Production Set from next Batch membership", async () => {
  const worker = await workerFor("fleet-page");
  const page = await worker.fetch(new Request("http://localhost/fleet", { headers: { accept: "text/html" } }), env, ctx);
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, /PMODE · FACTORY CONSOLE/);

  const route = await fs.readFile(new URL("../app/fleet/page.tsx", import.meta.url), "utf8");
  const source = await fs.readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
  const workspace = await fs.readFile(new URL("../app/workspace-session.tsx", import.meta.url), "utf8");
  const css = await fs.readFile(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
  const sharedPanel = await fs.readFile(new URL("../app/operator-ui/operator-panel.tsx", import.meta.url), "utf8");
  const sharedPanelCss = await fs.readFile(new URL("../app/operator-ui/operator-panel.css", import.meta.url), "utf8");
  const batchApi = await fs.readFile(new URL("../app/server-batch-api.ts", import.meta.url), "utf8");

  assert.match(route, /factory-console-v2/);
  assert.match(source, /PRODUCTION SITE SELECTION/);
  assert.match(source, /PROGRAMMING JOB/);
  assert.match(source, /LIVE SITE STATUS/);
  assert.match(source, /FACTORY LOG/);
  assert.match(source, /import \{ BatchSummary \} from "\.\.\/operator-ui\/batch-summary"/);
  assert.match(source, /<BatchSummary/);
  assert.doesNotMatch(source, /OperatorKpiStrip/);
  assert.match(source, /OperatorPanel/);
  assert.doesNotMatch(sharedPanel, /BatchSummary|OperatorKpiStrip|operatorKpiStrip/);
  assert.match(sharedPanel, /operatorPanel/);
  assert.match(sharedPanelCss, /\.operatorPanel/);

  assert.match(workspace, /pmodDraftSelection/);
  assert.match(workspace, /pmodProductionSet/);
  assert.match(workspace, /pmodBatchSelection/);
  assert.match(workspace, /ProductionSet = SelectionMap/);
  assert.match(workspace, /BatchSelection = SelectionMap/);
  assert.match(workspace, /draft = transient tree edit state/);
  assert.match(workspace, /Production Set = committed equipment scope/);
  assert.match(workspace, /Batch Selection = operator intent/);
  assert.match(workspace, /Server Batch Runtime remains server-owned/);

  assert.match(source, /applyProductionSet/);
  assert.match(source, /setProductionSet\(snapshot\)/);
  assert.match(source, /setBatchSelection\(snapshot\)/);
  assert.match(source, /const batchTargets = useMemo/);
  assert.match(source, /productionSet\[facilityId\]\?\.\[ppuId\]/);
  assert.match(source, /const serverBatchState = batchSnapshot\?\.state \?\? null/);
  assert.match(source, /displayedBatchSelection = serverBatchRunning \? serverBatchMembership : batchSelection/);
  assert.match(source, /label: "PROCESSED IC", value: manufacturing\.total/);
  assert.doesNotMatch(source, /setBatchState/);
  assert.match(source, /Batch select \$\{active\.target\.display_name\}/);
  assert.match(source, /Batch select \$\{active\.target\.display_name\} \$\{siteLabel\(site\.id\)\}/);
  assert.match(source, /toggleBatchFacility/);
  assert.match(source, /Batch select \$\{group\.facility\.display_name\}/);
  assert.match(source, /disabled=\{batchRunning \|\| !site\.enabled\}/);
  assert.match(source, /data-batch-selected=\{selected \? "true" : "false"\}/);

  assert.match(source, /<details className="productionTreeFacility"/);
  assert.match(source, /<details className="productionTreePpu"/);
  assert.match(source, /aria-expanded=\{!selectorCollapsed\}/);
  assert.match(css, /\.productionSiteSelection\.is-collapsed \.operatorPanelBody\s*\{\s*display:\s*none;/s);

  assert.match(source, /ICPickerField/);
  assert.match(source, /if \(!targetDevice && !syntheticMockImageAvailable\)/);
  assert.match(source, /targetDevice:\s*targetDevice \? \{ vendor: targetDevice\.vendor, identifier: targetDevice\.identifier \} : null/);
  assert.match(source, /allowSyntheticMockImage:\s*syntheticMockImageAvailable/);

  assert.match(source, /createServerBatch/);
  assert.match(source, /getServerBatch/);
  assert.match(source, /cancelServerBatch/);
  assert.doesNotMatch(source, /cancelServerBatchPPU/);
  assert.doesNotMatch(source, /Cancel PPU/);
  assert.match(source, /only whole-Batch ABORT is allowed/);
  assert.match(source, /batchSelectionLocked/);

  const abortFunction = source.slice(source.indexOf("async function abortBatch"), source.indexOf("function stateText"));
  assert.match(abortFunction, /cancelServerBatch\(/);
  assert.doesNotMatch(abortFunction, /ppu_id|site_id|cancelServerBatchPPU/);

  assert.match(source, /site\.completed_rounds/);
  assert.match(source, /site\.final_failures/);
  assert.match(source, /const total = pass \+ fail/);
  assert.doesNotMatch(source.slice(source.indexOf("const manufacturing = useMemo"), source.indexOf("const repeatValue")), /cancelled/);
  assert.match(source, /label: "SITES"/);
  assert.match(source, /label: "TOTAL IC"/);
  assert.match(source, /label: "PROCESSED IC"/);
  assert.match(source, /value: manufacturing\.total/);
  assert.match(source, /label: "PASS"/);
  assert.match(source, /label: "FAIL"/);
  assert.match(source, /label: "YIELD"/);
  assert.match(source, /label: "BATCH TIME"/);
  assert.match(source, /programmingJobCollapsed/);
  assert.match(source, /Collapse"\} Production Programming Job/);
  assert.match(source, /!programmingJobCollapsed && <div className="factoryJobGrid">/);

  assert.match(css, /--site-card-w/);
  assert.match(css, /density-dense/);
  assert.match(css, /\.factorySiteLedGrid\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /factorySiteLed\[data-state="ready"\]/);
  assert.match(css, /factorySiteLed\[data-state="running"\]/);
  assert.match(css, /factorySiteLed\[data-state="success"\]/);
  assert.match(css, /factorySiteLed\[data-state="faulted"\]/);
  assert.match(css, /factorySiteLed\[data-state="disabled"\]/);
  assert.match(css, /background:\s*#38bdf8/); // READY is not PASS green.
  assert.match(css, /background:\s*#f59e0b/); // RUNNING amber.
  assert.match(css, /background:\s*#22c55e/); // PASS green.
  assert.match(css, /background:\s*#ef4444/); // FAIL red.

  assert.match(batchApi, /"\/api\/batches"/);
  assert.match(batchApi, /terminalServerBatchStates/);

  const api = await worker.fetch(new Request("http://localhost/api/fleet", { headers: { accept: "application/json" } }), env, ctx);
  assert.equal(api.status, 404);
  const payload = await api.json();
  assert.equal(payload.error?.code, "fleet_ui_disabled");
});

test("fleet BFF source keeps Manager loopback-only and latest-job summaries browser-safe", async () => {
  const route = await fs.readFile(new URL("../app/api/fleet/route.ts", import.meta.url), "utf8");
  const contract = await fs.readFile(new URL("../app/fleet/fleet-contract.ts", import.meta.url), "utf8");
  const vite = await fs.readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  assert.match(route, /LOOPBACK_HOSTS/);
  assert.match(route, /must remain loopback-only/);
  assert.match(route, /export async function GET/);
  assert.doesNotMatch(route, /export async function (POST|PUT|PATCH|DELETE)/);
  assert.doesNotMatch(contract, /endpoint:\s*string/);
  assert.doesNotMatch(contract, /errors:\s*/);
  assert.match(contract, /last_known/);
  assert.match(contract, /current_capacity/);
  assert.match(contract, /latest_job/);
  assert.match(contract, /progress_percent/);
  assert.doesNotMatch(contract, /output_files/);
  assert.doesNotMatch(contract, /firmware/);
  assert.match(vite, /\^\/api\/\(\?!fleet/);
  assert.match(vite, /target: "http:\/\/127\.0\.0\.1:18080"/);
  assert.match(vite, /PLASMA_FLEET_UI_ENABLED:\s*process\.env\.PLASMA_FLEET_UI_ENABLED\s*\?\?\s*"0"/);
  assert.match(vite, /PLASMA_MANAGER_API_URL:\s*process\.env\.PLASMA_MANAGER_API_URL/);
  assert.match(vite, /vars:\s*fleetWorkerVars/);
  assert.match(vite, /nodejs_compat_populate_process_env/);
});