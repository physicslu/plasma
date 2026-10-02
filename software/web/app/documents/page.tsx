"use client";

import { useState, type ReactNode } from "react";
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
  | "emode-ppu-setup"
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
      { id: "emode-ppu-setup", label: "PPU Setup" },
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


type DocumentCalloutTone = "info" | "success" | "warning" | "critical";

function DocumentCallout({
  tone = "info",
  label,
  children,
}: {
  tone?: DocumentCalloutTone;
  label: string;
  children: ReactNode;
}) {
  const symbol = tone === "success" ? "✓" : tone === "warning" || tone === "critical" ? "!" : "i";
  return (
    <aside className={`documentCallout ${tone}`}>
      <span className="documentCalloutIcon" aria-hidden="true">{symbol}</span>
      <div><strong>{label}</strong><div>{children}</div></div>
    </aside>
  );
}

function DocumentDataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: string[][];
}) {
  return (
    <div className="documentDataTableWrap">
      <table className="documentDataTable">
        <thead><tr>{headers.map(header => <th key={header}>{header}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${row.join("-")}`}>
              {row.map((value, cellIndex) => <td key={`${cellIndex}-${value}`}>{value}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentSectionHeading({
  number,
  title,
  summary,
}: {
  number: number;
  title: string;
  summary: string;
}) {
  return (
    <header className="documentSectionHeading">
      <span>{number}</span>
      <div><h2>{title}</h2><p>{summary}</p></div>
    </header>
  );
}

function DocumentSetupOverview({
  title,
  subtitle,
  steps,
}: {
  title: string;
  subtitle: string;
  steps: Array<[string, string]>;
}) {
  return (
    <section className="documentSetupOverview" aria-label={title}>
      <header><span className="documentSetupOverviewIcon" aria-hidden="true">≡</span><div><h2>{title}</h2><p>{subtitle}</p></div></header>
      <div className="documentSetupStepGrid">
        {steps.map(([label, description], index) => (
          <div className="documentSetupStep" key={label}>
            <span>{index + 1}</span>
            <div><strong>{label}</strong><small>{description}</small></div>
          </div>
        ))}
      </div>
    </section>
  );
}

function PpuSetupExampleRail({ zh }: { zh: boolean }) {
  return (
    <aside className="documentExampleRail" aria-label={zh ? "PPU 操作畫面示例" : "PPU operation screen examples"}>
      <header className="documentExampleRailHeader">
        <span className="documentExampleRailIcon" aria-hidden="true">▣</span>
        <div>
          <small>{zh ? "操作畫面示例" : "OPERATION SCREEN EXAMPLES"}</small>
          <h2>{zh ? "操作畫面示例" : "Operation screen examples"}</h2>
          <p>{zh ? "以下是操作畫面的示意，用來對照左側步驟；不是即時系統狀態。" : "These are illustrative operation screens for following the steps at left; they are not live system state."}</p>
        </div>
      </header>

      <section className="documentOperationExample">
        <header><span>1</span><div><strong>{zh ? "新增 PPU 連線" : "Add a PPU connection"}</strong><p>{zh ? "PPU → Registration → + Add PPU Connection" : "PPU → Registration → + Add PPU Connection"}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "新增 PPU 連線示意畫面" : "Illustrative add PPU connection screen"}>
          <div className="documentMockToolbar"><b>Registration</b><span>+ Add PPU Connection</span></div>
          <div className="documentMockForm">
            <label><span>Console Alias</span><b>line1-ppu-a</b></label>
            <label><span>Plasma Gateway Endpoint</span><b>http://192.168.10.21:18080</b></label>
            <div className="documentMockActions"><span>Cancel</span><strong>Add Connection</strong></div>
          </div>
        </div>
      </section>

      <section className="documentOperationExample">
        <header><span>2</span><div><strong>{zh ? "查看 PPU 狀態" : "Review PPU state"}</strong><p>{zh ? "新增後確認 Connectivity、Health 與 Registration readiness。" : "After adding it, confirm Connectivity, Health, and Registration readiness."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "PPU 狀態示意畫面" : "Illustrative PPU status screen"}>
          <div className="documentMockToolbar"><b>Known PPU Connections</b><span>Refresh</span></div>
          <div className="documentMockStatusRow"><b>line1-ppu-a</b><span data-tone="good">Online</span><span data-tone="good">Healthy</span></div>
          <div className="documentMockSummary">
            <div><small>PPU ID</small><strong>ppu-8f2c9d7e</strong></div>
            <div><small>Registration</small><strong>Registered</strong></div>
            <div><small>Execution</small><strong>Ready</strong></div>
            <div><small>Reported Sites</small><strong>8</strong></div>
          </div>
        </div>
      </section>
    </aside>
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

  if (topic === "emode-ppu-setup") {
    const setupSteps: Array<[string, string]> = zh ? [
      ["連線 PPU", "建立 PPU Connection"],
      ["確認 PPU 狀態", "確認身分與健康"],
      ["註冊燒錄權限", "申請 Managed Programming admission"],
      ["選擇受管操作", "指定 Managed Operations PPU"],
      ["網路設定", "設定 Desired Network"],
      ["Platform 維護", "Bootstrap / Runtime 維護"],
      ["Site 設定與就緒", "設定 Sites 並確認 Runtime"],
    ] : [
      ["Connect PPU", "Create the PPU connection"],
      ["Confirm PPU state", "Verify identity and health"],
      ["Register programming", "Admit Managed Programming"],
      ["Select managed target", "Choose the Managed Operations PPU"],
      ["Configure network", "Set Desired Network"],
      ["Maintain Platform", "Maintain Bootstrap / Runtime"],
      ["Configure Sites & ready", "Configure Sites and confirm Runtime"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">EMODE · PPU SETUP</p>
          <h1>{zh ? "PPU 設定" : "PPU Setup"}</h1>
          <p className="documentLead">
            {zh
              ? "PPU Setup 說明如何連線並註冊 PPU，以及設定網路、Platform 與 Sites。先看完整步驟，再依序完成每個設定；每一步的操作畫面示例顯示在右側。"
              : "PPU Setup explains how to connect and register a PPU, then configure its network, Platform, and Sites. Review the complete flow first, then follow each step; operation-screen examples are shown at right."}
          </p>
        </header>

        <DocumentSetupOverview
          title={zh ? "設定總覽　共 7 個大步驟" : "Setup overview · 7 major steps"}
          subtitle={zh ? "先了解完整流程與工作量，再往下依序完成各步驟。" : "Review the whole flow and expected work before following the detailed procedure."}
          steps={setupSteps}
        />

        <DocumentCallout tone="success" label={zh ? "重點說明 (Key Points)" : "Key points"}>
          <ul>
            <li>{zh ? "PPU Connection / Registration、Platform Maintenance 與 Site Configuration 是獨立管理領域。" : "PPU Connection / Registration, Platform Maintenance, and Site Configuration are separate management domains."}</li>
            <li>{zh ? "Healthy 不代表所有 capability 都存在；Not Supported 也不代表 PPU 故障。" : "Healthy does not mean every capability exists, and Not Supported does not mean the PPU is faulty."}</li>
            <li>{zh ? "Registration 只控制 Managed Programming admission；Platform Maintenance 有獨立授權邊界。" : "Registration controls Managed Programming admission only; Platform Maintenance has a separate authorization boundary."}</li>
          </ul>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "連線 PPU" : "Connect the PPU"} summary={zh ? "將 PPU 加入 Control Station，建立已知連線。" : "Add the PPU to the Control Station as a known connection."} />
              <div className="documentSubsection">
                <h3><span>1.1</span>{zh ? "新增 PPU 連線" : "Add PPU Connection"}</h3>
                <p>{zh ? "進入 Engineering Mode → PPU → Registration，按 + Add PPU Connection，輸入下列資訊後按 Add Connection。" : "Open Engineering Mode → PPU → Registration, select + Add PPU Connection, enter the following values, then select Add Connection."}</p>
                <DocumentDataTable
                  headers={zh ? ["欄位", "說明", "範例"] : ["Field", "Description", "Example"]}
                  rows={[
                    ["Console Alias", zh ? "PPU 在此 Control Station 中的顯示名稱。" : "The PPU name used by this Control Station.", "line1-ppu-a"],
                    ["Plasma Gateway Endpoint", zh ? "PPU 的 Plasma Gateway root URL。" : "The root URL of the PPU Plasma Gateway.", "http://192.168.10.21:18080"],
                  ]}
                />
                <DocumentCallout label={zh ? "注意：僅建立 PPU Connection" : "Note — PPU Connection only"}>
                  <p>{zh ? "Add Connection 只讓 Control Station 知道這台 PPU；它通常仍為 Not Registered，尚未取得 Managed Programming admission。" : "Add Connection only makes the PPU known to the Control Station. It normally remains Not Registered and is not yet admitted to Managed Programming."}</p>
                </DocumentCallout>
                <DocumentCallout tone="warning" label={zh ? "不要混淆 Gateway 名稱" : "Do not confuse Gateway terms"}>
                  <p>{zh ? "Plasma Gateway Endpoint 是 Plasma service URL；Default Gateway 是 Linux 網路介面的 Layer-3 next-hop router。兩者不是同一個設定。" : "Plasma Gateway Endpoint is a Plasma service URL. Default Gateway is the Linux interface Layer-3 next-hop router. They are different settings."}</p>
                </DocumentCallout>
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "確認 PPU 狀態" : "Confirm PPU state"} summary={zh ? "確認 PPU 身分、連線與執行服務狀態符合 Registration 前提。" : "Verify identity, connectivity, and execution state before Registration."} />
              <p>{zh ? "新增 Connection 後，Manager 會取得 Fleet observation。確認 PPU ID、Facility、Reported Sites、Connectivity、Health 與 Active Execution 符合預期。" : "After adding the connection, Manager obtains Fleet observations. Confirm the PPU ID, Facility, Reported Sites, Connectivity, Health, and Active Execution state."}</p>
              <DocumentDataTable
                headers={zh ? ["檢查項目", "說明", "期望狀態"] : ["Check", "Description", "Expected state"]}
                rows={[
                  ["Observation current", zh ? "PPU observation 必須是目前有效資料。" : "The PPU observation must be current.", "Current"],
                  ["Transport reachable", zh ? "Manager 可以連到 Plasma Gateway。" : "Manager can reach the Plasma Gateway.", "Online"],
                  ["Execution ready", zh ? "PPU execution service 已 ready。" : "The PPU execution service is ready.", "Ready"],
                  ["No identity conflict", zh ? "沒有 canonical ppu_id 衝突。" : "No canonical ppu_id conflict is present.", "None"],
                  ["Not degraded", zh ? "Fleet observation 沒有 degraded condition。" : "Fleet observation reports no degraded condition.", "Healthy"],
                ]}
              />
              <DocumentCallout tone="success" label={zh ? "PPU 準備就緒" : "PPU readiness"}>
                <p>{zh ? "所有 Registration prerequisites 都通過後，才能進入下一步。Stale 或 Unknown observation 不足以註冊。" : "All Registration prerequisites must pass before continuing. Stale or Unknown observations are not sufficient for Registration."}</p>
              </DocumentCallout>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={3} title={zh ? "註冊燒錄權限" : "Register programming admission"} summary={zh ? "將 PPU 納入 Managed Programming。" : "Admit the PPU to Managed Programming."} />
              <div className="documentSubsection">
                <h3><span>3.1</span>{zh ? "Validate & Register for Programming" : "Validate & Register for Programming"}</h3>
                <p>{zh ? "當 Registration Readiness 全部通過後，按 Validate & Register for Programming。成功後 lifecycle 會成為 Commissioned，UI 顯示 Registered。" : "When all Registration Readiness checks pass, select Validate & Register for Programming. The lifecycle becomes Commissioned and the UI reports Registered."}</p>
              </div>
              <DocumentCallout tone="warning" label={zh ? "重要：Registration 與 Platform Maintenance 分離" : "Important — Registration is separate from Platform Maintenance"}>
                <p>{zh ? "Registration 只控制 Managed Programming admission，不會授權 Platform Maintenance。" : "Registration controls Managed Programming admission only; it does not authorize Platform Maintenance."}</p>
              </DocumentCallout>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={4} title={zh ? "選擇受管操作 PPU" : "Select the Managed Operations PPU"} summary={zh ? "指定目前 Managed Programming 的目標 PPU。" : "Choose the current target PPU for Managed Programming."} />
              <p>{zh ? "對已 Registered 的 PPU 按 Use for Managed Operations。之後 PMode / EMode 的 managed workflow 會透過 Manager 對這台 PPU 執行工作。" : "For a Registered PPU, select Use for Managed Operations. Managed PMode / EMode workflows then route through Manager to that PPU."}</p>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={5} title={zh ? "網路設定" : "Configure the PPU network"} summary={zh ? "設定 PPU Desired Network，並由 Manager 管理 Static IPv4 commissioning。" : "Configure Desired Network and let Manager own Static IPv4 commissioning."} />
              <p>{zh ? "完成 Registration 後，可在 PPU Network Configuration 查看 Interface、Desired Mode、Activation、Revision 與 Manager Txn。需要修改時按 Configure Network。" : "After Registration, PPU Network Configuration shows Interface, Desired Mode, Activation, Revision, and Manager Txn. Select Configure Network to edit it."}</p>
              <DocumentDataTable
                headers={zh ? ["模式 / 狀態", "說明", "操作重點"] : ["Mode / State", "Description", "Operator note"]}
                rows={[
                  ["DHCP", zh ? "保存 DHCP Desired State。" : "Stores DHCP Desired State.", zh ? "是否立即套用取決於 Network Activation capability。" : "Immediate application depends on Network Activation capability."],
                  ["Static IPv4", zh ? "設定 IPv4 Address、Prefix Length、Default Gateway 與 DNS Servers。" : "Configures IPv4 Address, Prefix Length, Default Gateway, and DNS Servers.", zh ? "由 Manager 擁有 commissioning transaction。" : "Manager owns the commissioning transaction."],
                  ["Not Supported", zh ? "此 PPU Profile 沒有 Network Activation capability。" : "The PPU profile does not expose Network Activation capability.", zh ? "Capability boundary，不是 runtime fault。" : "Capability boundary, not a runtime fault."],
                ]}
              />
              <p>{zh ? "Static IPv4 commissioning 流程為：保存 Desired → PPU 啟用候選位址 → Manager 重新連線候選 Endpoint → 驗證相同 ppu_id → PPU commit → Manager 更新 Plasma Gateway Endpoint。Browser 不直接改寫已註冊的 Endpoint。" : "Static IPv4 commissioning is Manager-owned: save Desired → PPU activates the candidate address → Manager reconnects to the candidate Endpoint → verifies the same ppu_id → PPU commits → Manager updates the Plasma Gateway Endpoint. The Browser does not directly rewrite the registered Endpoint."}</p>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={6} title={zh ? "Platform 維護" : "Maintain the Platform"} summary={zh ? "使用獨立的 Platform Maintenance boundary 維護 Bootstrap 與 Runtime。" : "Use the separate Platform Maintenance boundary for Bootstrap and Runtime maintenance."} />
              <p>{zh ? "進入 PPU → Platform。此頁負責 Bootstrap、Runtime、Platform Release、Platform Maintenance authorization 與 PS Loop Test；與 Programming Registration lifecycle 分離。" : "Open PPU → Platform. This surface owns Bootstrap, Runtime, Platform Release, Platform Maintenance authorization, and the PS Loop Test; it is separate from the Programming Registration lifecycle."}</p>
              <div className="documentCompactProcedure">
                {(zh ? [
                  "選擇已知 PPU 並確認 Bootstrap / Platform capability",
                  "輸入 Platform Maintenance Pairing Token 並完成授權",
                  "選擇 Platform Release package 與 SHA-256 sidecar",
                  "確認 PPU ID / Facility ID / Display Name",
                  "按 Update PPU Platform Release",
                  "等待 Runtime Active，必要時執行 Run PS Loop Test",
                ] : [
                  "Select a known PPU and confirm Bootstrap / Platform capability",
                  "Enter the Platform Maintenance Pairing Token and authorize maintenance",
                  "Select the Platform Release package and SHA-256 sidecar",
                  "Confirm PPU ID / Facility ID / Display Name",
                  "Select Update PPU Platform Release",
                  "Wait for Runtime Active and run the PS Loop Test when needed",
                ]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
              <DocumentCallout label={zh ? "Platform Maintenance · Not Supported" : "Platform Maintenance · Not Supported"}>
                <p>{zh ? "代表此 PPU Profile 沒有 Bootstrap / Platform Maintenance route；這是 capability boundary，不是 fault。" : "The PPU profile does not expose the Bootstrap / Platform Maintenance route. This is a capability boundary, not a fault."}</p>
              </DocumentCallout>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={7} title={zh ? "Site 設定與就緒確認" : "Configure Sites and confirm readiness"} summary={zh ? "設定 Site Desired Configuration，必要時套用 Runtime，再確認可進入 Programming。" : "Configure Site Desired State, apply Runtime when needed, then confirm Programming readiness."} />
              <div className="documentSubsection">
                <h3><span>7.1</span>{zh ? "Site Configuration" : "Site Configuration"}</h3>
                <p>{zh ? "進入 PPU → Sites。Ready / Busy / Fault / Enabled Sites / Topology Source / Active Execution 是 Observed Runtime State；是否能修改 Site Desired Configuration 是另一個 capability。" : "Open PPU → Sites. Ready / Busy / Fault / Enabled Sites / Topology Source / Active Execution are Observed Runtime State. Site Desired Configuration write support is a separate capability."}</p>
                <DocumentDataTable
                  headers={zh ? ["設定", "說明", "注意"] : ["Setting", "Description", "Note"]}
                  rows={[
                    ["Desired Enabled", zh ? "Site 是否應啟用。" : "Whether the Site should be enabled.", zh ? "保存到 Desired Configuration。" : "Stored in Desired Configuration."],
                    ["Desired Interface", zh ? "Site programming interface，例如 mock、openocd 或 fpga。" : "Site programming interface, such as mock, openocd, or fpga.", zh ? "Accepted values 由 PPU contract 決定。" : "Accepted values are defined by the PPU contract."],
                    ["Desired Target", zh ? "Site target configuration identity。" : "Site target configuration identity.", zh ? "不代表實體 IC 已完成 qualification。" : "Does not prove physical IC qualification."],
                  ]}
                />
                <p>{zh ? "Plasma 明確區分 Draft → Desired → Runtime。Save 只更新 Desired Configuration，不代表 running Plasma Server 已套用。" : "Plasma explicitly separates Draft → Desired → Runtime. Save updates Desired Configuration only; it does not mean the running Plasma Server has applied it."}</p>
              </div>
              <div className="documentSubsection">
                <h3><span>7.2</span>{zh ? "Runtime Activation" : "Runtime Activation"}</h3>
                <p>{zh ? "若 PPU 支援 Runtime Activation，可按 Activate Desired Configuration。這是 PPU-level 操作；有 active Site execution 時會被拒絕。" : "If the PPU supports Runtime Activation, select Activate Desired Configuration. This is a PPU-level operation and is rejected while Site execution is active."}</p>
                <DocumentCallout label={zh ? "Runtime Activation · Not Supported" : "Runtime Activation · Not Supported"}>
                  <p>{zh ? "表示目前 PPU Profile 沒有此 capability，而不是 runtime fault。" : "The current PPU profile does not expose this capability; it is not a runtime fault."}</p>
                </DocumentCallout>
              </div>
              <div className="documentSubsection">
                <h3><span>7.3</span>{zh ? "狀態判讀" : "State interpretation"}</h3>
                <DocumentDataTable
                  headers={zh ? ["狀態", "意義", "Operator 判讀"] : ["State", "Meaning", "Operator interpretation"]}
                  rows={[
                    ["Healthy", zh ? "沒有已知 degraded condition。" : "No known degraded condition.", zh ? "不代表所有 capability 都存在。" : "Does not imply every capability exists."],
                    ["Registered", zh ? "Managed Programming admission 完成。" : "Managed Programming admission is complete.", zh ? "仍不等於 Platform Maintenance Authorized。" : "Still does not mean Platform Maintenance is authorized."],
                    ["Not Supported", zh ? "此 PPU Profile 沒有該 capability。" : "The PPU profile does not expose the capability.", zh ? "不是 Fault。" : "Not a Fault."],
                    ["Not Installed", zh ? "Capability 存在，但 Runtime 尚未安裝。" : "Capability exists, but Runtime is not installed.", zh ? "需要 Platform deployment。" : "Platform deployment is required."],
                    ["Unavailable", zh ? "應可取得的狀態目前無法取得。" : "Expected state cannot currently be observed.", zh ? "需要診斷。" : "Diagnose the failure."],
                    ["Busy / Fault", zh ? "正在執行或已有 fault evidence。" : "Execution is active or fault evidence exists.", zh ? "依狀態停止變更並進行診斷。" : "Avoid unsafe changes and diagnose as appropriate."],
                  ]}
                />
              </div>
              <DocumentCallout tone="critical" label={zh ? "Evidence boundary" : "Evidence boundary"}>
                <p>{zh ? "Mock PPU 的 Online / Healthy / Site Ready 只證明相應 software / Mock workflow；不代表 Z2、FPGA/PL、socket、電氣條件或實體 IC programming 已完成驗證。" : "Online / Healthy / Site Ready on a Mock PPU proves only the corresponding software / Mock workflow. It does not validate Z2, FPGA/PL, sockets, electrical behavior, or physical IC programming."}</p>
              </DocumentCallout>
            </section>
          </div>

          <PpuSetupExampleRail zh={zh} />
        </div>
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
        <p className="documentLead">{zh ? "以下只列目前 Gateway Settings UI 可以直接修改的欄位。" : "Only fields that are directly editable in the current Gateway Settings UI are listed below."}</p>
        <DefinitionTable rows={[
          ["PPU Request Timeout", zh ? "單次 PPU request 的等待時間。預設 10 秒，可設定 1–120 秒。" : "Wait time for one PPU request. Default 10 seconds; range 1–120 seconds."],
          ["PPU Retry Count", zh ? "暫時性 PPU 通訊錯誤的追加重試次數。預設 3，可設定 0–10；retry backoff 由系統自動管理，不可設定。" : "Additional retries for transient PPU communication errors. Default 3; range 0–10. Retry backoff is system-managed and is not configurable."],
        ]} />
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