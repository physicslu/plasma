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
  assert.match(html, />Choose Product Mode</);
  assert.match(html, /href="\/fleet"/);
  assert.match(html, />Production Mode</);
  assert.match(html, /href="\/engineering"/);
  assert.match(html, />Engineering Mode</);
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

test("fleet implementation route exposes the Production Console while cross-PPU writes remain locked", async () => {
  const worker = await workerFor("fleet-page");
  const page = await worker.fetch(new Request("http://localhost/fleet", { headers: { accept: "text/html" } }), env, ctx);
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, />Factory Production Console</);
  assert.match(html, />PRODUCTION MODE</);
  assert.match(html, /跨 PPU 寫入需另行啟用受認證控制路徑/);
  assert.match(html, /<button[^>]*disabled[^>]*>執行批次<\/button>/);
  assert.match(html, />Factory Log Console</);

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
