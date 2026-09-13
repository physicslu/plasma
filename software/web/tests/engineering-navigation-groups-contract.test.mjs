import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = new URL("../app/engineering/page.tsx", import.meta.url);
const stylePath = new URL("../app/engineering/engineering-nav-groups.css", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("Engineering navigation groups daily workflow, troubleshooting, and advanced surfaces without changing section identity", async () => {
  const [page, css] = await Promise.all([source(pagePath), source(stylePath)]);

  assert.match(page, /overview: \{ "zh-TW": "主要工作", "en-US": "WORKFLOW" \}/);
  assert.match(page, /diagnostics: \{ "zh-TW": "疑難排解", "en-US": "TROUBLESHOOTING" \}/);
  assert.match(page, /tools: \{ "zh-TW": "進階設定", "en-US": "ADVANCED" \}/);
  assert.match(page, /\["overview", "engineering\.overview", "⌂"\][\s\S]*\["ppu-sites", "engineering\.ppuSites", "▤"\][\s\S]*\["programming", "engineering\.programming", "▶"\][\s\S]*\["diagnostics", "engineering\.diagnostics", "∿"\][\s\S]*\["logs", "engineering\.logs", "▧"\][\s\S]*\["tools", "engineering\.tools", "⌘"\][\s\S]*\["settings", "engineering\.settings", "⚙"\]/);
  assert.match(page, /System Configuration/);
  assert.match(page, /Mock Runtime · Simulation only/);
  assert.match(page, /className="engineeringNavGroupLabel"/);
  assert.match(css, /\.engineeringPage\.sidebarCollapsed \.engineeringNavGroupLabel[\s\S]*display:\s*none/);

  for (const forbidden of [
    "createServerBatch",
    "cancelServerBatch",
    "fetch(",
    "sessionStorage",
    "localStorage",
  ]) {
    assert.equal(css.includes(forbidden), false, `navigation grouping stylesheet must remain presentation-only: ${forbidden}`);
  }
});
