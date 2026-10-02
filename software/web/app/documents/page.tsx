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
    return (
      <article className="documentArticle">
        <p className="documentEyebrow">EMODE · PPU SETUP</p>
        <h1>{zh ? "PPU 設定" : "PPU Setup"}</h1>
        <p className="documentLead">
          {zh
            ? "PPU 是 Plasma 實際執行燒錄工作的設備。Control Station 必須先知道 PPU 的 Plasma Gateway Endpoint，確認 PPU 身分與運作狀態，再決定是否允許它進入 Managed Programming。PPU Connection / Registration、Platform Maintenance 與 Site Configuration 是三個彼此獨立的管理領域。"
            : "A PPU is the appliance that executes Plasma programming work. The Control Station must first know its Plasma Gateway Endpoint, observe its identity and health, and then decide whether to admit it to Managed Programming. PPU Connection / Registration, Platform Maintenance, and Site Configuration are separate management domains."}
        </p>

        <section>
          <h2>{zh ? "管理領域" : "Management domains"}</h2>
          <DefinitionTable rows={[
            ["PPU Connection / Registration", zh ? "Control Station 是否知道這台 PPU，以及是否允許它執行 Managed Programming。" : "Whether the Control Station knows the PPU and admits it to Managed Programming."],
            ["Platform Maintenance", zh ? "Bootstrap、Runtime、Platform Release 與維護授權；與 Programming Registration 分離。" : "Bootstrap, Runtime, Platform Release, and maintenance authorization; separate from Programming Registration."],
            ["Site Configuration", zh ? "PPU 各 Site 的 Desired Configuration、Runtime reconciliation 與 Runtime Activation。" : "Desired Configuration, Runtime reconciliation, and Runtime Activation for the PPU Sites."],
          ]} />
          <aside className="documentNotice">
            {zh
              ? "Healthy 不代表所有 capability 都存在；Not Supported 也不代表 PPU 故障。"
              : "Healthy does not mean every capability exists, and Not Supported does not mean the PPU is faulty."}
          </aside>
        </section>

        <section>
          <h2>{zh ? "1. 加入 PPU Connection" : "1. Add a PPU Connection"}</h2>
          <p>{zh ? "進入 Engineering Mode → PPU → Registration，按 + Add PPU Connection。" : "Open Engineering Mode → PPU → Registration, then select + Add PPU Connection."}</p>
          <DefinitionTable rows={[
            ["Console Alias", zh ? "Control Station 內使用的 PPU 名稱，例如 line1-ppu-a。" : "The PPU name used by this Control Station, for example line1-ppu-a."],
            ["Plasma Gateway Endpoint", zh ? "PPU Plasma Gateway 的 root URL，例如 http://192.168.10.21:18080。" : "The root URL of the PPU Plasma Gateway, for example http://192.168.10.21:18080."],
          ]} />
          <p>{zh ? "按 Add Connection 後，PPU 只會成為 Control Station 已知的 Connection；它通常仍是 Not Registered，尚未取得 Managed Programming admission。" : "After Add Connection, the PPU is only a known Control Station connection. It normally remains Not Registered and is not yet admitted to Managed Programming."}</p>
          <aside className="documentNotice">
            {zh
              ? "Plasma Gateway Endpoint 是 Plasma service URL；Default Gateway 是 Linux 介面的 Layer-3 next-hop router。兩者不是同一個設定。"
              : "Plasma Gateway Endpoint is a Plasma service URL. Default Gateway is the Linux interface Layer-3 next-hop router. They are different settings."}
          </aside>
        </section>

        <section>
          <h2>{zh ? "2. 確認 PPU 狀態" : "2. Confirm PPU State"}</h2>
          <p>{zh ? "加入 Connection 後，Manager 會取得 Fleet observation。進行 Programming Registration 前，先確認 PPU ID、Facility、Reported Sites、Connectivity、Health 與 Active Execution 符合預期。" : "After adding the connection, Manager obtains Fleet observations. Before Programming Registration, confirm the PPU ID, Facility, Reported Sites, Connectivity, Health, and Active Execution state."}</p>
          <DefinitionTable rows={[
            ["Observation current", zh ? "PPU observation 必須是目前有效資料；stale 或 unknown 不足以進行 Registration。" : "The PPU observation must be current; stale or unknown data is not sufficient for Registration."],
            ["Transport reachable", zh ? "Manager 可以連到 Plasma Gateway。" : "Manager can reach the Plasma Gateway."],
            ["Execution ready", zh ? "PPU execution service 已進入 ready 狀態。" : "The PPU execution service reports ready."],
            ["No identity conflict", zh ? "沒有 canonical ppu_id 衝突。" : "No canonical ppu_id conflict is present."],
            ["Not degraded", zh ? "Fleet observation 沒有 degraded condition。" : "Fleet observation reports no degraded condition."],
          ]} />
        </section>

        <section>
          <h2>{zh ? "3. Register PPU for Programming" : "3. Register the PPU for Programming"}</h2>
          <p>{zh ? "當 Registration Readiness 全部通過後，按 Validate & Register for Programming。成功後 lifecycle 會成為 Commissioned，UI 顯示 Registered。" : "When all Registration Readiness checks pass, select Validate & Register for Programming. The lifecycle becomes Commissioned and the UI reports Registered."}</p>
          <p>{zh ? "Registration 只控制 Managed Programming admission，不會授權 Platform Maintenance。" : "Registration controls Managed Programming admission only; it does not authorize Platform Maintenance."}</p>
        </section>

        <section>
          <h2>{zh ? "4. 選擇 Managed Operations PPU" : "4. Select the PPU for Managed Operations"}</h2>
          <p>{zh ? "對已 Registered 的 PPU 按 Use for Managed Operations，將它設為目前 Managed Programming 使用的 PPU。之後 PMode / EMode 的 managed workflow 會透過 Manager 對該 PPU 執行工作。" : "For a Registered PPU, select Use for Managed Operations to make it the current managed-programming target. Managed PMode / EMode workflows then route through Manager to that PPU."}</p>
        </section>

        <section>
          <h2>{zh ? "5. PPU Network Configuration" : "5. PPU Network Configuration"}</h2>
          <p>{zh ? "完成 Programming Registration 後，可在 Registration 頁面的 PPU Network Configuration 查看 Interface、Desired Mode、Activation、Revision 與 Manager Txn。需要修改時按 Configure Network。" : "After Programming Registration, PPU Network Configuration shows Interface, Desired Mode, Activation, Revision, and Manager Txn. Select Configure Network to edit it."}</p>
          <DefinitionTable rows={[
            ["DHCP", zh ? "保存 DHCP Desired State。是否能立即套用取決於 PPU 是否提供 Network Activation capability。" : "Stores DHCP Desired State. Immediate application depends on whether the PPU exposes Network Activation capability."],
            ["Static IPv4", zh ? "可設定 IPv4 Address、Prefix Length、Default Gateway 與 DNS Servers。" : "Configures IPv4 Address, Prefix Length, Default Gateway, and DNS Servers."],
            ["Not Supported", zh ? "此 PPU Profile 沒有 Network Activation capability；這是 capability boundary，不是 runtime fault。" : "This PPU profile does not expose Network Activation capability. This is a capability boundary, not a runtime fault."],
          ]} />
          <p>{zh ? "Static IPv4 commissioning 由 Manager 擁有交易流程：保存 Desired → PPU 啟用候選位址 → Manager 重新連線候選 Endpoint → 驗證相同 ppu_id → PPU commit → Manager 更新 Plasma Gateway Endpoint。Browser 不直接改寫已註冊的 Endpoint。" : "Static IPv4 commissioning is Manager-owned: save Desired → PPU activates the candidate address → Manager reconnects to the candidate Endpoint → verifies the same ppu_id → PPU commits → Manager updates the Plasma Gateway Endpoint. The Browser does not directly rewrite the registered Endpoint."}</p>
        </section>

        <section>
          <h2>{zh ? "6. Platform Maintenance" : "6. Platform Maintenance"}</h2>
          <p>{zh ? "進入 PPU → Platform。這個頁面負責 Bootstrap、Runtime、Platform Release、Platform Maintenance authorization 與 PS Loop Test。Platform lifecycle 與 Programming Registration 分離。" : "Open PPU → Platform. This surface owns Bootstrap, Runtime, Platform Release, Platform Maintenance authorization, and the PS Loop Test. The Platform lifecycle is separate from Programming Registration."}</p>
          <Flow steps={zh
            ? ["選擇已知 PPU", "確認 Bootstrap / Platform capability", "輸入 Platform Maintenance Pairing Token", "Authorize Platform Maintenance", "選擇 Platform Release package 與 SHA-256 sidecar", "確認 PPU ID / Facility ID / Display Name", "Update PPU Platform Release", "等待 Runtime Active 並視需要執行 PS Loop Test"]
            : ["Select a known PPU", "Confirm Bootstrap / Platform capability", "Enter the Platform Maintenance Pairing Token", "Authorize Platform Maintenance", "Select the Platform Release package and SHA-256 sidecar", "Confirm PPU ID / Facility ID / Display Name", "Update PPU Platform Release", "Wait for Runtime Active and run the PS Loop Test when needed"]} />
          <aside className="documentNotice">
            {zh
              ? "若顯示 Platform Maintenance · Not Supported，代表此 PPU Profile 沒有 Bootstrap / Platform Maintenance route。這不是 fault。"
              : "Platform Maintenance · Not Supported means the PPU profile does not expose the Bootstrap / Platform Maintenance route. It is not a fault."}
          </aside>
        </section>

        <section>
          <h2>{zh ? "7. Site Configuration" : "7. Site Configuration"}</h2>
          <p>{zh ? "進入 PPU → Sites。上方 Ready / Busy / Fault / Enabled Sites / Topology Source / Active Execution 是 Observed Runtime State；是否能修改 Site Desired Configuration 是另一個 capability。" : "Open PPU → Sites. Ready / Busy / Fault / Enabled Sites / Topology Source / Active Execution are Observed Runtime State. Site Desired Configuration write support is a separate capability."}</p>
          <DefinitionTable rows={[
            ["Desired Enabled", zh ? "Site 是否應在 Desired Configuration 中啟用。" : "Whether the Site should be enabled in Desired Configuration."],
            ["Desired Interface", zh ? "Site 使用的 programming interface，例如 mock、openocd 或 fpga；可用值仍由 PPU contract 決定。" : "The programming interface, such as mock, openocd, or fpga; the PPU contract remains authoritative for accepted values."],
            ["Desired Target", zh ? "Site 的 target configuration identity；不代表該實體 IC 已完成 qualification。" : "The Site target configuration identity; it is not proof that a physical IC is qualified."],
          ]} />
          <p>{zh ? "Plasma 明確區分 Draft → Desired → Runtime。Save 只更新 Desired Configuration，不代表 running Plasma Server 已套用。" : "Plasma explicitly separates Draft → Desired → Runtime. Save updates Desired Configuration only; it does not mean the running Plasma Server has applied it."}</p>
        </section>

        <section>
          <h2>{zh ? "8. Runtime Activation" : "8. Runtime Activation"}</h2>
          <p>{zh ? "如果 PPU 支援 Runtime Activation，可按 Activate Desired Configuration。這是 PPU-level 操作：關閉新的 Job admission、restart Plasma Server、重新載入 canonical Site Desired Configuration，再驗證 PPU identity 與 Runtime reconciliation。" : "If the PPU supports Runtime Activation, select Activate Desired Configuration. This is a PPU-level operation: quiesce new Job admission, restart Plasma Server, reload canonical Site Desired Configuration, then verify PPU identity and Runtime reconciliation."}</p>
          <p>{zh ? "有 active Site execution 時 Activation 會被拒絕。若顯示 Runtime Activation · Not Supported，代表目前 PPU Profile 沒有此 capability，而不是 runtime fault。" : "Activation is rejected while Site execution is active. Runtime Activation · Not Supported means the current PPU profile does not expose this capability; it is not a runtime fault."}</p>
        </section>

        <section>
          <h2>{zh ? "9. 常見狀態判讀" : "9. Interpreting Common States"}</h2>
          <DefinitionTable rows={[
            ["Healthy", zh ? "目前沒有已知 degraded condition；不代表所有 capability 都存在。" : "No known degraded condition is reported; this does not imply every capability exists."],
            ["Registered", zh ? "已通過 Managed Programming admission。" : "Managed Programming admission is complete."],
            ["Not Registered", zh ? "尚未通過 Programming Registration。" : "Programming Registration has not completed."],
            ["Not Supported", zh ? "此 PPU Profile 沒有該 capability。" : "The PPU profile does not expose that capability."],
            ["Not Installed", zh ? "相關 capability 存在，但 Runtime 尚未安裝。" : "The relevant capability exists, but Runtime is not installed."],
            ["Unavailable", zh ? "理論上應可取得狀態，但目前無法取得；需要當成可診斷的異常。" : "The state should be observable but is currently unavailable and should be diagnosed."],
            ["Busy", zh ? "PPU 或 Site 正在執行工作。" : "The PPU or Site is executing work."],
            ["Fault", zh ? "已有明確的 runtime / Site fault evidence。" : "Explicit runtime or Site fault evidence exists."],
          ]} />
          <aside className="documentNotice">
            {zh
              ? "Healthy ≠ 所有 capability 都存在；Not Supported ≠ Fault；Registered ≠ Platform Maintenance Authorized。"
              : "Healthy ≠ every capability exists; Not Supported ≠ Fault; Registered ≠ Platform Maintenance Authorized."}
          </aside>
        </section>

        <section>
          <h2>{zh ? "10. 建議的初次設定流程" : "10. Recommended First-Time Setup"}</h2>
          <h3>{zh ? "已有 Runtime 的 PPU" : "PPU with Runtime already installed"}</h3>
          <Flow steps={zh
            ? ["確認 PPU 網路可達", "Add PPU Connection", "確認 PPU ID / Connectivity / Health", "Validate & Register for Programming", "Use for Managed Operations", "視需要設定 Network", "檢查 Sites topology", "視 capability 設定 Site Desired Configuration", "視需要執行 Runtime Activation", "進入 Programming 驗證"]
            : ["Confirm PPU network reachability", "Add PPU Connection", "Confirm PPU ID / Connectivity / Health", "Validate & Register for Programming", "Use for Managed Operations", "Configure Network when needed", "Inspect Sites topology", "Configure Site Desired Configuration when supported", "Run Runtime Activation when needed", "Proceed to Programming validation"]} />
          <h3>{zh ? "Bootstrap-only PPU" : "Bootstrap-only PPU"}</h3>
          <Flow steps={zh
            ? ["完成 PPU Bootstrap factory provisioning", "Add PPU Connection", "進入 Platform", "Authorize Platform Maintenance", "部署 PPU Platform Release / Runtime", "確認 Runtime Active", "回到 Registration", "Validate & Register for Programming", "設定 Sites", "進行 Programming qualification"]
            : ["Complete PPU Bootstrap factory provisioning", "Add PPU Connection", "Open Platform", "Authorize Platform Maintenance", "Deploy the PPU Platform Release / Runtime", "Confirm Runtime Active", "Return to Registration", "Validate & Register for Programming", "Configure Sites", "Run Programming qualification"]} />
        </section>

        <aside className="documentNotice critical">
          {zh
            ? "Mock PPU 的 Online / Healthy / Site Ready 只證明相應的 software / Mock workflow。它不代表 Z2、FPGA/PL、socket、電氣條件或實體 IC programming 已完成驗證。"
            : "Online / Healthy / Site Ready on a Mock PPU proves only the corresponding software / Mock workflow. It does not validate Z2, FPGA/PL, sockets, electrical behavior, or physical IC programming."}
        </aside>
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