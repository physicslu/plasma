import assert from "node:assert/strict";
import test from "node:test";

test("renders the Plasma Control Station product entry", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/demo", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  const html = await response.text();
  assert.match(html, /<html\s+lang=["']zh-Hant["']/i);
  assert.match(html, /<title>Plasma Control Station<\/title>/i);
  assert.match(html, />PLASMA</);
  assert.match(html, />選擇產品模式</);
  assert.match(html, /href="\/fleet"/);
  assert.match(html, />量產模式</);
  assert.match(html, /href="\/engineering"/);
  assert.match(html, />工程模式</);
  assert.doesNotMatch(html, />SITE MATRIX</);
  assert.doesNotMatch(html, />PPU CONTROL</);
});
