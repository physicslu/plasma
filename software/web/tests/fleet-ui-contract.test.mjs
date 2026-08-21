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
  assert.doesNotMatch(nav, /nav\.fleet/);
  assert.doesNotMatch(nav, /nav\.singlePpu/);
});

test("fleet implementation uses retained FPS selection, four-column PPU layout and running LED feedback", async () => {
  const worker = await workerFor("fleet-page");
  const page = await worker.fetch(new Request("http://localhost/fleet", { headers: { accept: "text/html" } }), env, ctx);
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, />Factory Production Console</);
  assert.match(html, /PRODUCTION MODE · MOCK PROTOTYPE/);

  const source = await fs.readFile(new URL("../app/fleet/page.tsx", import.meta.url), "utf8");
  const css = await fs.readFile(new URL("../app/fleet/production-prototype.css", import.meta.url), "utf8");
  const operatorFeedback = await fs.readFile(new URL("../app/fleet/operator-feedback.css", import.meta.url), "utf8");
  assert.match(source, /type SelectionMap/);
  assert.match(source, /draftSelection/);
  assert.match(source, /activeSelection/);
  assert.match(source, /clearAll:\s*"全部取消"/);
  assert.match(source, /apply:\s*"確定選取"/);
  assert.match(source, /liveStatus:\s*"Active FPS : 即時執行狀態"/);
  assert.match(source, /fpsSelectorCommandGroup/);
  assert.match(source, /applyFpsSelection/);
  assert.match(source, /groupedActiveTargets/);
  assert.match(source, /data-production-facility/);
  assert.match(source, /densityFor/);
  assert.doesNotMatch(source, /setSelectorCollapsed\(true\)/);
  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /runSiteSequence/);
  assert.match(source, /cancelPPU/);
  assert.match(source, /site\.state === "running" \? ` · \$\{site\.progress\}%`/);
  assert.match(css, /background:\s*#f5f8fc/);
  assert.match(css, /--site-tile-w/);
  assert.match(css, /density-dense/);
  assert.match(css, /width:\s*var\(--site-tile-w\)/);
  assert.match(css, /height:\s*var\(--site-tile-h\)/);
  assert.match(operatorFeedback, /grid-template-columns:\s*repeat\(4,\s*var\(--site-tile-w\)\)/);
  assert.match(operatorFeedback, /--ppu-card-w/);
  assert.match(operatorFeedback, /production-site-running-pulse/);
  assert.match(operatorFeedback, /\.prototypeSiteLamp\.running i/);
  assert.match(operatorFeedback, /\.fpsSelectionSummary\s*\{\s*display:\s*none;/s);
  assert.match(operatorFeedback, /content:\s*"Cancel All"/);
  assert.match(operatorFeedback, /content:\s*"Confirm"/);
  assert.match(operatorFeedback, /\.productionImagePicker\s*\{[^}]*grid-template-columns:\s*max-content\s+max-content\s+minmax\(0,\s*1fr\)/s);
  assert.match(operatorFeedback, /\.productionImagePicker\s*>\s*\.productionBrowseButton\s*\{[^}]*grid-column:\s*2;[^}]*grid-row:\s*1;/s);
  assert.match(operatorFeedback, /\.facilityRuntimeIdentity h3\s*\{[^}]*font-weight:\s*800;/s);

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
