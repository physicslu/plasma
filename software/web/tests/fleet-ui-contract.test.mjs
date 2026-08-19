import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

async function workerFor(name) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${name}-${process.pid}-${Date.now()}`);
  return (await import(workerUrl.href)).default;
}

const env = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};
const ctx = {
  waitUntil() {},
  passThroughOnException() {},
};

test("public Plasma host sends root users to the two-demo landing page", async () => {
  const worker = await workerFor("demo-root");
  const response = await worker.fetch(
    new Request("https://plasma.open4th.com/", { headers: { accept: "text/html" }, redirect: "manual" }),
    env,
    ctx,
  );
  assert.ok([301, 302, 307, 308].includes(response.status));
  assert.equal(new URL(response.headers.get("location"), "https://plasma.open4th.com").pathname, "/demo");
});

test("non-public local root keeps the original PPU console behavior", async () => {
  const worker = await workerFor("local-root");
  const response = await worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    env,
    ctx,
  );
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, />SITE MATRIX</);
});

test("demo landing page exposes Single PPU and Manager/Fleet links", async () => {
  const worker = await workerFor("demo-page");
  const response = await worker.fetch(
    new Request("http://localhost/demo", { headers: { accept: "text/html" } }),
    env,
    ctx,
  );
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, />Choose a Demo</);
  assert.match(html, /href="\/ppu"/);
  assert.match(html, />Single PPU Demo</);
  assert.match(html, /href="\/fleet"/);
  assert.match(html, />Manager \/ Fleet Demo</);
});

test("fleet page is read-only and fleet API is opt-in by default", async () => {
  const worker = await workerFor("fleet-page");
  const page = await worker.fetch(
    new Request("http://localhost/fleet", { headers: { accept: "text/html" } }),
    env,
    ctx,
  );
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, />Facility \/ PPU Fleet Overview</);
  assert.match(html, />READ-ONLY CONTROL PLANE</);

  const api = await worker.fetch(
    new Request("http://localhost/api/fleet", { headers: { accept: "application/json" } }),
    env,
    ctx,
  );
  assert.equal(api.status, 404);
  const payload = await api.json();
  assert.equal(payload.error?.code, "fleet_ui_disabled");
});

test("fleet BFF source enforces loopback Manager and strips internal endpoint/error fields", async () => {
  const route = await fs.readFile(new URL("../app/api/fleet/route.ts", import.meta.url), "utf8");
  const contract = await fs.readFile(new URL("../app/fleet/fleet-contract.ts", import.meta.url), "utf8");

  assert.match(route, /LOOPBACK_HOSTS/);
  assert.match(route, /must remain loopback-only/);
  assert.match(route, /export async function GET/);
  assert.doesNotMatch(route, /export async function (POST|PUT|PATCH|DELETE)/);
  assert.doesNotMatch(contract, /endpoint:\s*string/);
  assert.doesNotMatch(contract, /errors:\s*/);
  assert.match(contract, /last_known/);
  assert.match(contract, /current_capacity/);
});
