"use client";

import { useState } from "react";
import { useI18n } from "../i18n";
import "../engineering/engineering.css";
import "../engineering/engineering-workspace-refresh.css";
import "./documents.css";

type Topic =
  | "pmode-overview"
  | "pmode-flow"
  | "pmode-programming"
  | "pmode-batch"
  | "emode-overview"
  | "emode-flow"
  | "emode-programming"
  | "gateway-settings"
  | "mock-settings";

type Section = "pmode" | "emode";

const NAVIGATION: Array<{
  id: Section;
  label: string;
  icon: string;
  topics: Array<{ id: Topic; label: string }>;
}> = [
  {
    id: "pmode",
    label: "PMode",
    icon: "▦",
    topics: [
      { id: "pmode-overview", label: "Overview" },
      { id: "pmode-flow", label: "Operation Flow" },
      { id: "pmode-programming", label: "Programming Job" },
      { id: "pmode-batch", label: "Batch & Status" },
    ],
  },
  {
    id: "emode",
    label: "EMode",
    icon: "◇",
    topics: [
      { id: "emode-overview", label: "Overview" },
      { id: "emode-flow", label: "Operation Flow" },
      { id: "emode-programming", label: "Programming" },
      { id: "gateway-settings", label: "Gateway Settings" },
      { id: "mock-settings", label: "Mock Settings" },
    ],
  },
];

function Flow({ steps }: { steps: string[] }) {
  return (
    <div className="documentFlow" aria-label="Operation flow">
      {steps.map((step, index) => (
        <div className="documentFlowStep" key={step}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <b>{step}</b>
        </div>
      ))}
    </div>
  );
}

function DefinitionTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="documentDefinitionTable">
      {rows.map(([name, description]) => (
        <div className="documentDefinitionRow" key={name}>
          <b>{name}</b>
          <span>{description}</span>
        </div>
      ))}
    </div>
  );
}

function TopicContent({ topic, zh }: { topic: Topic; zh: boolean }) {
  if (topic === "pmode-overview") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">PMODE · PRODUCTION OPERATION</p>
        <h1>{zh ? "PMode 操作總覽" : "PMode Overview"}</h1>
        <p className="documentLead">{zh ? "PMode 是 Production Mode（量產模式），用於正式燒錄與批次量產作業。Operator 先選定 Facility / PPU / Site，再以單一 Programming Job 定義 Target IC、Programming Image、E/P/V/R 與 Batch Policy。" : "PMode means Production Mode. It is used for production programming and batch operations: select Facility / PPU / Site scope, then define Target IC, Programming Image, E/P/V/R, and Batch Policy in one Programming Job."}</p>
        <section><h2>{zh ? "核心物件" : "Core objects"}</h2><DefinitionTable rows={[
          ["Facility", zh ? "設備所在的產線、實驗室或管理區域。" : "The line, lab, or managed area that owns PPUs."],
          ["PPU", zh ? "實際執行燒錄工作的 PPU。" : "The PPU that executes programming work."],
          ["Site", zh ? "PPU 上可獨立執行工作的實體燒錄位置。" : "An independently executable programming position on a PPU."],
          ["Programming Job", zh ? "Target IC、Image、Operations 與 Batch Policy 的工作定義。" : "The work definition containing Target IC, Image, Operations, and Batch Policy."],
          ["Batch", zh ? "START 後由 Server 擁有與追蹤的執行實例。" : "The server-owned execution instance created after START."],
        ]} /></section>
        <aside className="documentNotice">{zh ? "PMode 的 UI 是操作介面；真正的 PPU execution ownership、Batch state 與結果判定仍以 backend 為準。" : "The PMode UI is an operator surface. Backend execution ownership, Batch state, and result truth remain authoritative."}</aside>
      </article>
    );
  }

  if (topic === "pmode-flow") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">PMODE · OPERATION FLOW</p>
        <h1>{zh ? "PMode 操作流程" : "PMode Operation Flow"}</h1>
        <Flow steps={zh ? ["選擇 Facility / PPU / Site", "選擇 Target IC", "選擇 Programming Image", "勾選 Erase / Program / Verify / Read", "設定 Batch Policy", "確認 BATCH READY", "START PROGRAMMING", "監看 Live Site Status", "確認 Batch Summary"] : ["Select Facility / PPU / Site", "Select Target IC", "Select Programming Image", "Choose Erase / Program / Verify / Read", "Set Batch Policy", "Confirm BATCH READY", "START PROGRAMMING", "Monitor Live Site Status", "Review Batch Summary"]} />
        <section><h2>{zh ? "執行原則" : "Execution rules"}</h2><ul><li>{zh ? "START 後 Batch membership 凍結，不能用切換模式或重新選 Site 來改變正在執行的 Batch。" : "Batch membership is frozen after START."}</li><li>{zh ? "執行中以 whole-Batch ABORT 作為主要停止操作。" : "Whole-Batch ABORT is the primary runtime stop action."}</li><li>{zh ? "同一 PPU 同時間最多只有一個 active execution owner。" : "A PPU has at most one active execution owner at a time."}</li></ul></section>
      </article>
    );
  }

  if (topic === "pmode-programming") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">PMODE · PROGRAMMING JOB</p>
        <h1>{zh ? "Programming Job 設定" : "Programming Job Settings"}</h1>
        <DefinitionTable rows={[
          ["Target IC", zh ? "本次工作要操作的 IC。真實 provider 執行時必須能對應到受支援的 target。" : "The IC target for this work. Real-provider execution must resolve to a supported target."],
          ["Programming Image", zh ? "要寫入或驗證的 Programming Image。Program / Verify 需要有效 Image。" : "The Programming Image used for Program / Verify operations."],
          ["Erase", zh ? "擦除目標可程式化儲存區。" : "Erase the target programmable storage."],
          ["Program", zh ? "把 Programming Image 寫入目標。" : "Write the Programming Image to the target."],
          ["Verify", zh ? "比對目標內容與 Programming Image。" : "Compare target content with the Programming Image."],
          ["Read", zh ? "讀回 target-defined Main Flash 或對應可讀區域。" : "Read back the target-defined Main Flash or readable region."],
          ["Repeat", zh ? "每個已選 Site 預計處理的 IC 次數。Mock 可模擬多顆 IC；真實硬體仍需要實體換料/交接機制。" : "Planned IC count per selected Site. Mock can simulate repeats; real hardware still requires physical device handoff."],
          ["Site Retry Limit", zh ? "可信任的單 Site 操作失敗後允許的 Job retry 次數；不是 Gateway 通訊 retry。" : "Job retry count after a trusted Site operation failure; it is not Gateway communication retry."],
          ["Stop Policy", zh ? "當 retry-exhausted FAULTED Sites 達條件時，決定是否停止後續 Batch 工作。" : "Determines when retry-exhausted FAULTED Sites stop subsequent Batch work."],
        ]} />
      </article>
    );
  }

  if (topic === "pmode-batch") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">PMODE · BATCH & STATUS</p>
        <h1>{zh ? "Batch 指標與狀態" : "Batch Metrics and Status"}</h1>
        <section><h2>Batch Summary</h2><DefinitionTable rows={[
          ["SITES", zh ? "START 時凍結的已選 Site 數。" : "Selected Site count frozen at START."],
          ["TOTAL IC", zh ? "SITES × Repeat，代表計畫處理數。" : "SITES × Repeat, the planned IC quantity."],
          ["PROCESSED IC", zh ? "PASS + FAIL；基礎設施 ERROR 不計入。" : "PASS + FAIL; infrastructure ERROR is excluded."],
          ["PASS", zh ? "完整計畫 round 成功的 IC 數。" : "IC count with a successful complete round."],
          ["FAIL", zh ? "具有可信任 DUT / Site 失敗證據的 IC 數。" : "IC count with trusted DUT / Site failure evidence."],
          ["YIELD", zh ? "PASS / (PASS + FAIL)。沒有可信任結果時顯示 —。" : "PASS / (PASS + FAIL). Shows — before trusted results exist."],
          ["BATCH TIME", zh ? "Batch 從開始到現在或 terminal 的經過時間。" : "Elapsed Batch time until now or terminal state."],
        ]} /></section>
        <section><h2>{zh ? "Site 狀態" : "Site states"}</h2><DefinitionTable rows={[
          ["READY", zh ? "可加入下一個 Batch。" : "Available for the next Batch."],
          ["RUNNING", zh ? "已接受 Job 尚未 terminal。" : "An accepted Job is still active."],
          ["PASS / SUCCESS", zh ? "計畫工作完成且成功。" : "Planned work completed successfully."],
          ["FAIL / FAULTED", zh ? "可信任的 DUT / Site 燒錄失敗。" : "Trusted DUT / Site programming failure."],
          ["ERROR", zh ? "Gateway、PPU 通訊或 runtime 基礎設施異常；不是 IC FAIL。" : "Gateway, PPU communication, or runtime infrastructure failure; not an IC FAIL."],
          ["STOPPED", zh ? "因 stop policy 或相關基礎設施條件未繼續。" : "Execution did not continue because of stop policy or infrastructure conditions."],
          ["CANCELLED", zh ? "Operator ABORT / cancel 已完成。" : "Operator ABORT / cancel completed."],
        ]} /></section>
        <aside className="documentNotice critical">IC FAIL ≠ Infrastructure ERROR</aside>
      </article>
    );
  }

  if (topic === "emode-overview") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">EMODE · ENGINEERING OPERATION</p>
        <h1>{zh ? "EMode 操作總覽" : "EMode Overview"}</h1>
        <p className="documentLead">{zh ? "EMode 是 Engineering Mode（工程模式），用於工程開發、驗證、診斷與設定。它保留與 PMode 共用的 Programming Job 語意，但增加 Facility / PPU targeting、單 Site 操作、診斷資訊、Gateway 與 Mock 設定。" : "EMode means Engineering Mode. It is used for engineering development, validation, diagnostics, and configuration while sharing Programming Job semantics with PMode and adding targeting, direct Site actions, Gateway, and Mock settings."}</p>
        <section><h2>{zh ? "使用原則" : "Operating principles"}</h2><ul><li>{zh ? "先確認 Facility / PPU，再解讀 Site 狀態與 Job log。" : "Resolve Facility / PPU before interpreting Site state and Job logs."}</li><li>{zh ? "Direct single-Site Job 與 server-owned Batch 是不同 execution owner。" : "Direct single-Site Jobs and server-owned Batches are different execution owners."}</li><li>{zh ? "EMode 提供更多診斷資訊，但不能繞過 backend 的 PPU ownership 與授權。" : "Engineering diagnostics do not bypass backend PPU ownership or authorization."}</li></ul></section>
      </article>
    );
  }

  if (topic === "emode-flow") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">EMODE · OPERATION FLOW</p>
        <h1>{zh ? "EMode 操作流程" : "EMode Operation Flow"}</h1>
        <Flow steps={zh ? ["選擇 Facility", "選擇 PPU", "確認 Site 狀態", "選擇 Target IC / Programming Image", "選擇 E/P/V/R", "執行 Batch 或單 Site 操作", "監看 Site / Job / Operator Log", "必要時 Retry / Cancel / Diagnose"] : ["Select Facility", "Select PPU", "Confirm Site state", "Select Target IC / Programming Image", "Choose E/P/V/R", "Run Batch or direct Site operation", "Monitor Site / Job / Operator Log", "Retry / Cancel / Diagnose when needed"]} />
      </article>
    );
  }

  if (topic === "emode-programming") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">EMODE · PROGRAMMING</p>
        <h1>{zh ? "EMode Programming" : "EMode Programming"}</h1>
        <p className="documentLead">{zh ? "Programming Job 的 Target IC、Programming Image、Operations、Batch Policy 與 PMode 共用相同概念。EMode 額外提供工程 targeting、Site diagnostic table、直接單 Site 操作與完整 audit log。" : "Programming Job fields share the same concepts as PMode. EMode adds engineering targeting, a diagnostic Site table, direct single-Site actions, and full audit evidence."}</p>
        <aside className="documentNotice">{zh ? "同一個 operational concept 應採相同規則；EMode 的差異主要是工程診斷與直接操作，不是另一套 Programming Job 定義。" : "The same operational concept follows the same rules; EMode differs mainly in diagnostics and direct operations, not a second Programming Job definition."}</aside>
      </article>
    );
  }

  if (topic === "gateway-settings") {
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">EMODE · SETTINGS · GATEWAY</p>
        <h1>{zh ? "Gateway 設定說明" : "Gateway Settings"}</h1>
        <DefinitionTable rows={[
          ["PPU Request Timeout", zh ? "單次 PPU request 的等待時間。預設 10 秒，可設定 1–120 秒。" : "Wait time for one PPU request. Default 10 seconds; range 1–120 seconds."],
          ["PPU Retry Count", zh ? "可重試的 PPU observation request 次數。預設 3，所以最多為 1 次原始 request + 3 次 retry。" : "Retry count for retryable PPU observation requests. Default 3, for up to 1 original request + 3 retries."],
          ["Retry Backoff", zh ? "目前採 1、2、4 秒；後續 retry 維持 4 秒。" : "Currently 1, 2, and 4 seconds; later retries remain at 4 seconds."],
          ["PPU Response Budget", zh ? "Gateway 依 Timeout、Retry 與 backoff 推導的唯讀值。預設為 47 秒，不是第三個可寫 timeout。" : "Read-only value derived from timeout, retries, and backoff. Default 47 seconds; not a third writable timeout."],
          ["Browser Watchdog", zh ? "Browser 外層 transport watchdog 會再加 margin；它不擁有 PPU retry policy。" : "The browser adds an outer transport margin; it does not own the PPU retry policy."],
        ]} />
        <section><h2>{zh ? "預設 response budget" : "Default response budget"}</h2><pre className="documentFormula">4 × 10 sec + 1 + 2 + 4 sec = 47 sec</pre></section>
        <aside className="documentNotice critical">{zh ? "Job submission 不應因結果不確定而自動重送，避免重複建立 Job。" : "Job submission must not be blindly retried after an uncertain result, to avoid duplicate Jobs."}</aside>
      </article>
    );
  }

  return (
    <article className="documentArticle">
      <p className="documentEyebrow">EMODE · SETTINGS · MOCK</p>
      <h1>{zh ? "Mock 設定說明" : "Mock Settings"}</h1>
      <p className="documentLead">{zh ? "以下只列目前 Mock Settings UI 可以直接修改的欄位。" : "Only fields that are directly editable in the current Mock Settings UI are listed below."}</p>
      <DefinitionTable rows={[
        ["Enabled", zh ? "開啟或關閉 Profile timing / error injection。" : "Enable or disable Profile timing and error injection."],
        ["Default Image Size", zh ? "Mock Synthetic Programming Image 的預設大小，可設定 64–4096 KiB，step 為 64 KiB。" : "Default Mock Synthetic Programming Image size, configurable from 64 to 4096 KiB in 64 KiB steps."],
        ["Seed Mode", zh ? "可選 Auto 或 Fixed；Fixed 用於需要重現相同測試條件的情境。" : "Choose Auto or Fixed. Fixed is useful when the same controlled test condition must be reproduced."],
        ["Fixed Seed", zh ? "Seed Mode = Fixed 時可設定非負整數 seed；Auto 模式時此欄位不可編輯。" : "When Seed Mode is Fixed, configure a non-negative integer seed; this field is disabled in Auto mode."],
        ["E/P/V/R Error Rate", zh ? "Erase / Program / Verify / Read 各自可設定 0–100% 的 operation failure rate，解析度 0.1%；不是 Gateway/network 斷線率。" : "Each Erase / Program / Verify / Read operation has a configurable 0–100% failure rate at 0.1% resolution; this is not a Gateway or network disconnect rate."],
        ["E/P/V/R Base Time", zh ? "每個 operation 可設定基礎模擬執行時間，單位 ms。" : "Configure the base simulated execution time for each operation in milliseconds."],
        ["E/P/V/R Throughput", zh ? "每個 operation 可設定模擬 throughput，UI 單位為 KiB/s。" : "Configure simulated throughput for each operation; the UI uses KiB/s."],
        ["E/P/V/R Jitter", zh ? "每個 operation 可設定額外的 ± timing variation，單位 ms。" : "Configure additional ± timing variation for each operation in milliseconds."],
      ]} />
      <aside className="documentNotice critical">{zh ? "Mock PASS ≠ 真實 OpenOCD、Z2/FPGA、socket 或實體 IC programming 已驗證。" : "Mock PASS ≠ validation of real OpenOCD, Z2/FPGA, socket, or physical IC programming."}</aside>
    </article>
  );
}

export default function DocumentsPage() {
  const { locale } = useI18n();
  const zh = locale === "zh-TW";
  const [activeTopic, setActiveTopic] = useState<Topic>("pmode-overview");
  const [expanded, setExpanded] = useState<Record<Section, boolean>>({ pmode: true, emode: true });
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <main className={`engineeringPage documentsPage ${sidebarCollapsed ? "sidebarCollapsed" : ""}`} data-route-marker="Documents">
      <section className="engineeringShell">
        <div className="engineeringWorkspace documentsWorkspace">
          <aside className="engineeringSidebar">
            <header className="engineeringBrand">
              <span className="engineeringBrandMark" aria-hidden="true">≡</span>
              <div>
                <strong>Docs</strong>
                <span>PLASMA</span>
                <h1>{zh ? "操作文件" : "Operator Documents"}</h1>
              </div>
            </header>

            <nav aria-label={zh ? "文件導覽" : "Documents navigation"}>
              {NAVIGATION.map(section => {
                const sectionActive = section.topics.some(topic => topic.id === activeTopic);
                return (
                  <div className="engineeringNavTreeGroup" key={section.id}>
                    <button
                      type="button"
                      className={sectionActive ? "active" : ""}
                      aria-expanded={expanded[section.id]}
                      onClick={() => setExpanded(value => ({ ...value, [section.id]: !value[section.id] }))}
                    >
                      <span className="engineeringNavIcon" aria-hidden="true">{section.icon}</span>
                      <span className="engineeringNavLabel">{section.label}</span>
                      <span className="engineeringNavDisclosure" aria-hidden="true">{expanded[section.id] ? "⌄" : "›"}</span>
                    </button>
                    {expanded[section.id] && (
                      <div className="engineeringNavChildren" role="group" aria-label={section.label}>
                        {section.topics.map((topic, index) => (
                          <button
                            key={topic.id}
                            type="button"
                            className={activeTopic === topic.id ? "active" : ""}
                            aria-pressed={activeTopic === topic.id}
                            onClick={() => setActiveTopic(topic.id)}
                          >
                            <span className="engineeringNavTreeBranch" aria-hidden="true">{index === section.topics.length - 1 ? "└" : "├"}</span>
                            <span className="engineeringNavLabel">{topic.label}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </nav>

            <button
              type="button"
              className="engineeringSidebarCollapse"
              aria-label={sidebarCollapsed ? "Expand Documents menu" : "Collapse Documents menu"}
              onClick={() => setSidebarCollapsed(value => !value)}
            >
              <span aria-hidden="true">{sidebarCollapsed ? "»" : "«"}</span>
              <span className="engineeringNavLabel">Collapse</span>
            </button>
          </aside>

          <section className="engineeringCanvas documentsCanvas">
            <TopicContent topic={activeTopic} zh={zh} />
          </section>
        </div>
      </section>
    </main>
  );
}
