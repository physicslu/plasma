import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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
});

test("supports selected-channel batch jobs and per-channel controls", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /visibleChannelIds/);
  assert.match(page, /Promise\.all\(visibleChannelIds\.map/);
  assert.match(page, /runChannel\(channel\.id, operation\)/);
  assert.match(page, /主畫面至少必須保留一個通道/);
  assert.match(page, /disabled=\{locked\}/);
  assert.match(page, /待命 <b>\{statusCounts\.idle\}/);
  assert.match(page, /工作中 <b>\{statusCounts\.busy\}/);
  assert.match(page, /成功 <b>\{statusCounts\.success\}/);
  assert.match(page, /失敗 <b>\{statusCounts\.failed\}/);
  assert.match(page, /停用 <b>\{statusCounts\.disabled\}/);
});
