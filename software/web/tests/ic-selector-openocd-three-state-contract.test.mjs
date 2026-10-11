import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const selector = () => fs.readFile(new URL("../app/devices/ic-selector.tsx", import.meta.url), "utf8");
const styles = () => fs.readFile(new URL("../app/devices/devices.css", import.meta.url), "utf8");

test("the third of the original four IC status tags has exactly three display states", async () => {
  const source = await selector();
  assert.match(source, /type OpenOcdTagState = "mapped" \| "candidate" \| "no_mapping"/);
  assert.match(source, /if \(device\.backend\.mapping_status === "mapped"\) return "mapped"/);
  assert.match(source, /device\.backend\.mapping_status === "no_mapping"/);
  assert.match(source, /device\.backend_candidate\?\.status === "research_only"/);
  assert.match(source, /device\.backend_candidate\.executable === false/);
  assert.match(source, /device\.backend_candidate\.production_binding_authorized === false/);
  assert.match(source, /device\.backend_candidate\.hardware_runtime_ready === false/);
  assert.match(source, /device\.backend_candidate\.family === device\.family/);
  assert.match(source, /OpenOCD 設定 · 已存在/);
  assert.match(source, /OpenOCD 設定 · 候選/);
  assert.match(source, /OpenOCD 設定 · 未建立/);
  assert.match(source, /openOcdConfigLabel\(openOcdTagState\(device\), zh\)/);
  assert.doesNotMatch(source, /openOcdConfigLabel\(device\.backend\.mapping_status, zh\)/);
  assert.match(source, /icSelectorStatusPhysical/);
  assert.match(source, /icSelectorStatusEvidence/);
  assert.doesNotMatch(source, /icSelectorCandidateHint/);
});

test("mapped is green, candidate amber and no mapping neutral without granting programming", async () => {
  const source = await selector();
  const css = await styles();
  assert.match(source, /openOcdTagState\(device\) === "mapped" \? "verified"/);
  assert.match(source, /openOcdTagState\(device\) === "candidate" \? "pending" : "unmapped"/);
  assert.match(css, /\.icSelectorStatusRow \.verified \{/);
  assert.match(css, /\.icSelectorStatusRow \.pending \{/);
  assert.match(css, /\.icSelectorStatusRow \.unmapped \{/);
  assert.match(source, /Backend Candidate Registry · 尚不可燒錄/);
  assert.match(source, /selected\.backend\.mapping_status/);
  assert.match(source, /原廠料號 · 已確認/);
  assert.match(source, /未實機測試/);
});
