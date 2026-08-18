import assert from "node:assert/strict";
import test from "node:test";

test("renders the Plasma PPU Console shell before topology discovery", async () => {
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
  assert.match(html, /<title>Plasma PPU Console<\/title>/i);
  assert.match(html, />PLASMA</);
  assert.match(html, />SITE MATRIX</);
  assert.match(html, />深色</);
  assert.match(html, />淺色</);
  assert.match(html, /class="active"[^>]*aria-pressed="true"[^>]*>淺色</);
  assert.match(html, />Plasma Web REST Gateway</);
  assert.match(html, /aria-label="Plasma Web REST Gateway URL"/);
  assert.match(html, /<small>Plasma Web REST Gateway<\/small>/);
  assert.match(html, />DISPLAY SITES</);
  assert.match(html, /aria-label="Site 配置摘要"/);
  assert.match(html, />BATCH CONTROL</);
  assert.match(html, /aria-label="選取批次操作"/);
  assert.match(html, /aria-label="批次執行：尚未選擇操作"[^>]*disabled/);
  assert.match(html, />批次執行（0）</);
  assert.match(html, />LIVE SITE STATUS</);
  assert.match(html, />獨立操作</);
});
