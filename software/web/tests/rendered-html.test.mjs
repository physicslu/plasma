import assert from "node:assert/strict";
import test from "node:test";

test("renders the Plasma programmer console", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", {
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
  assert.match(html, /<title>Plasma Programmer Console<\/title>/i);
  assert.match(html, />PLASMA</);
  assert.match(html, />CHANNEL MATRIX</);
  assert.match(html, />CH<!-- -->0</);
  assert.match(html, />CH<!-- -->7</);
  assert.match(html, />深色</);
  assert.match(html, />淺色</);
  assert.match(html, /class="active"[^>]*aria-pressed="true"[^>]*>淺色</);
  assert.match(html, />PYTHON MOCK API</);
  assert.match(html, /aria-label="Python API URL"/);
  assert.match(html, />PYTHON GATEWAY</);
});
