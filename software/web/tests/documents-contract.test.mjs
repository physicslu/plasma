import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const demo = await readFile(new URL("../app/demo/page.tsx", import.meta.url), "utf8");
const i18n = await readFile(new URL("../app/i18n.tsx", import.meta.url), "utf8");
const documents = await readFile(new URL("../app/documents/page.tsx", import.meta.url), "utf8");
const documentsCss = await readFile(new URL("../app/documents/documents.css", import.meta.url), "utf8");

test("Documents is the fourth portal function and remains outside Product Mode", () => {
  assert.match(demo, /<span>04<\/span>/);
  assert.match(demo, /href="\/documents"/);
  assert.match(demo, /<h2>\{zh \? "文件" : "Documents"\}<\/h2>/);
  assert.doesNotMatch(documents, /setProductMode|ProductMode/);
});

test("portal copy explains PMode and EMode without implementation-architecture prose", () => {
  assert.match(i18n, /PMode（Production Mode／量產模式）/);
  assert.match(i18n, /EMode（Engineering Mode／工程模式）/);
  assert.match(i18n, /PMode \(Production Mode\)/);
  assert.match(i18n, /EMode \(Engineering Mode\)/);
  assert.doesNotMatch(i18n, /多 PPU aggregation、Manager 與單機 PPU Console 都是模式底下的實作能力/);
  assert.doesNotMatch(i18n, /Multi-PPU aggregation, Manager, and the standalone PPU Console are implementation capabilities/);
});

test("Documents is static operator content with no API or runtime document backend", () => {
  assert.doesNotMatch(documents, /fetch\(/);
  assert.doesNotMatch(documents, /apiBase|\/api\//);
  assert.doesNotMatch(documents, /markdown|remark|rehype/i);
  assert.match(documents, /TopicContent/);
  assert.match(documents, /PMode/);
  assert.match(documents, /EMode/);
});

test("Documents reuses the EMode sidebar presentation instead of defining a second sidebar skin", () => {
  assert.match(documents, /import "\.\.\/engineering\/engineering\.css"/);
  assert.match(documents, /import "\.\.\/engineering\/engineering-workspace-refresh\.css"/);
  assert.match(documents, /className="engineeringSidebar"/);
  assert.match(documents, /className="engineeringNavTreeGroup"/);
  assert.match(documents, /className="engineeringNavChildren"/);
  assert.doesNotMatch(documentsCss, /\.engineeringSidebar\s*\{/);
});

test("Documents v1 covers PMode, EMode, Gateway and Mock operator reference", () => {
  for (const required of [
    "pmode-overview",
    "pmode-flow",
    "pmode-programming",
    "pmode-batch",
    "emode-overview",
    "emode-ppu-setup",
    "emode-flow",
    "emode-programming",
    "gateway-settings",
    "mock-settings",
  ]) assert.match(documents, new RegExp(required));

  assert.match(documents, /IC FAIL ≠ Infrastructure ERROR/);
  assert.match(documents, /Mock PASS ≠/);
  assert.match(documents, /0\.1%/);
});

test("EMode PPU setup guide documents the current management boundaries and setup flow", () => {
  assert.match(documents, /PPU Setup/);
  assert.match(documents, /PPU Connection \/ Registration/);
  assert.match(documents, /Platform Maintenance/);
  assert.match(documents, /Site Configuration/);
  assert.match(documents, /Validate & Register for Programming/);
  assert.match(documents, /Use for Managed Operations/);
  assert.match(documents, /Plasma Gateway Endpoint/);
  assert.match(documents, /Default Gateway/);
  assert.match(documents, /Configure Network/);
  assert.match(documents, /Static IPv4 commissioning is Manager-owned/);
  assert.match(documents, /Authorize Platform Maintenance/);
  assert.match(documents, /Update PPU Platform Release/);
  assert.match(documents, /run the PS Loop Test when needed/i);
  assert.match(documents, /Draft → Desired → Runtime/);
  assert.match(documents, /Activate Desired Configuration/);
  assert.match(documents, /Healthy (?:≠|does not mean) every capability exists/);
  assert.match(documents, /Not Supported does not mean the PPU is faulty/);
  assert.match(documents, /\["Not Supported"[\s\S]*"Not a Fault\."/);
  assert.match(documents, /\["Registered"[\s\S]*Still does not mean Platform Maintenance is authorized/);
  assert.match(documents, /Bootstrap-only PPU/);
  assert.match(documents, /Mock PPU/);
  assert.match(documents, /physical IC programming/);
});

test("PPU Setup is the first structured document-layout migration", () => {
  for (const primitive of [
    "DocumentSetupOverview",
    "DocumentSectionHeading",
    "DocumentDataTable",
    "DocumentCallout",
    "PpuSetupExampleRail",
  ]) assert.match(documents, new RegExp(primitive));

  assert.match(documents, /設定總覽　共 7 個大步驟/);
  assert.match(documents, /Setup overview · 7 major steps/);
  for (const step of [
    "連線 PPU",
    "確認 PPU 狀態",
    "註冊燒錄權限",
    "選擇受管操作",
    "網路設定",
    "Platform 維護",
    "Site 設定與就緒",
  ]) assert.match(documents, new RegExp(step));

  assert.match(documents, /操作畫面示例/);
  assert.match(documents, /不是即時系統狀態/);
  assert.match(documents, /documentExampleRail/);
  assert.doesNotMatch(documents, /On this page/);

  for (const className of [
    "documentArticleGuide",
    "documentSetupOverview",
    "documentSetupStepGrid",
    "documentGuideBody",
    "documentProcedureSection",
    "documentExampleRail",
    "documentCompactProcedure",
  ]) assert.match(documentsCss, new RegExp(`\\.${className}`));
});

test("Gateway operator reference lists only currently editable settings", () => {
  assert.match(documents, /\["PPU Request Timeout"/);
  assert.match(documents, /\["PPU Retry Count"/);
  assert.doesNotMatch(documents, /\["Retry Backoff"/);
  assert.doesNotMatch(documents, /\["PPU Response Budget"/);
  assert.doesNotMatch(documents, /\["Browser Watchdog"/);
  assert.doesNotMatch(documents, /Default response budget|預設 response budget/);
  assert.doesNotMatch(documents, /4 × 10 sec \+ 1 \+ 2 \+ 4 sec = 47 sec/);
  assert.doesNotMatch(documents, /Job submission 不應因結果不確定而自動重送/);
});

test("Mock operator reference lists only currently editable settings", () => {
  for (const editable of [
    "Enabled",
    "Default Image Size",
    "Seed Mode",
    "Fixed Seed",
    "E/P/V/R Error Rate",
    "E/P/V/R Base Time",
    "E/P/V/R Throughput",
    "E/P/V/R Jitter",
  ]) assert.match(documents, new RegExp(editable.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  assert.doesNotMatch(documents, /\["Synthetic Image"/);
  assert.doesNotMatch(documents, /\["Applied Configuration"/);
});
