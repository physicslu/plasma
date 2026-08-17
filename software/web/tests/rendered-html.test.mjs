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
  assert.match(html, />DISPLAY CHANNELS</);
  assert.match(html, /aria-label="通道配置摘要"/);
  assert.match(html, /<span>停用 <b>6<\/b><\/span>/);
  assert.match(html, /aria-label="顯示 CH0"/);
  assert.match(html, /aria-label="顯示 CH7"/);
  assert.match(html, />BATCH CONTROL</);
  assert.match(html, /aria-label="選取批次操作"/);
  assert.match(html, /aria-label="批次執行：尚未選擇操作"[^>]*disabled/);
  assert.match(html, />批次執行（0）</);
  assert.match(html, />LIVE CHANNEL STATUS</);
  assert.match(html, />獨立操作</);
  assert.match(html, /aria-label="CH0 擦除"/);
  assert.match(html, /aria-label="CH1 讀取"/);
});
