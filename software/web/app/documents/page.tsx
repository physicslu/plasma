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

type DocumentExampleSpec = {
  title: string;
  caption: string;
  toolbar: string;
  toolbarMeta: string;
  fields?: Array<[string, string]>;
  summary?: Array<[string, string]>;
  statusRows?: Array<{ label: string; value: string; detail?: string; good?: boolean }>;
  primaryAction?: string;
  secondaryAction?: string;
};

function DocumentTopicExampleRail({ topic, zh }: { topic: Topic; zh: boolean }) {
  let examples: DocumentExampleSpec[] = [];

  if (topic === "pmode-overview" || topic === "pmode-flow") {
    examples = [
      {
        title: zh ? "選擇 Production Set" : "Select the Production Set",
        caption: zh ? "先決定 Facility / PPU / Site 範圍。" : "Define the Facility / PPU / Site scope first.",
        toolbar: "Production Site Selection",
        toolbarMeta: "Production Set",
        summary: [["Facility", "line-1"], ["PPU", "line1-ppu-a"], ["Sites", "8"], ["Selected", "8"]],
      },
      {
        title: zh ? "定義 Programming Job" : "Define the Programming Job",
        caption: zh ? "Target IC、Image、Operations 與 Batch Policy 集中在同一工作面板。" : "Target IC, Image, Operations, and Batch Policy stay in one work panel.",
        toolbar: "Programming Job",
        toolbarMeta: "BATCH READY",
        fields: [["Target IC", "Selected IC"], ["Programming Image", "firmware.bin"], ["Operations", "ERASE → PROGRAM → VERIFY"], ["Repeat / Retry", "1 / 3"]],
        primaryAction: "START PROGRAMMING",
      },
      {
        title: zh ? "監看 Batch 與 Sites" : "Monitor Batch and Sites",
        caption: zh ? "START 後以 Batch Summary 與 Live Site Status 追蹤執行結果。" : "After START, use Batch Summary and Live Site Status to track execution.",
        toolbar: "BATCH SUMMARY",
        toolbarMeta: "Current Batch",
        summary: [["SITES", "8"], ["TOTAL IC", "8"], ["PROCESSED IC", "8"], ["YIELD", "100%"]],
        statusRows: [{ label: "Live Site Status", value: "PASS", detail: "8 / 8", good: true }],
      },
    ];
  } else if (topic === "pmode-programming") {
    examples = [
      {
        title: zh ? "選擇 Target 與 Image" : "Choose Target and Image",
        caption: zh ? "Program / Verify 需要有效 Programming Image。" : "Program / Verify require a valid Programming Image.",
        toolbar: "Programming Job",
        toolbarMeta: "Target",
        fields: [["Target IC", "Selected IC"], ["Programming Image", "firmware.bin"]],
      },
      {
        title: zh ? "選擇 Operations" : "Choose Operations",
        caption: zh ? "Erase / Program / Verify / Read 依本次工作需要組合。" : "Combine Erase / Program / Verify / Read as required for the job.",
        toolbar: "Operations",
        toolbarMeta: "E / P / V / R",
        fields: [["Erase", "Enabled"], ["Program", "Enabled"], ["Verify", "Enabled"], ["Read", "Disabled"]],
      },
      {
        title: zh ? "設定 Batch Policy" : "Set Batch Policy",
        caption: zh ? "Repeat、Retry 與 Stop Policy 決定本次 Batch 的執行政策。" : "Repeat, Retry, and Stop Policy define Batch execution policy.",
        toolbar: "Batch Policy",
        toolbarMeta: "Ready",
        fields: [["Repeat", "1"], ["Retry", "3"], ["Stop Policy", "Off"]],
        primaryAction: "START PROGRAMMING",
      },
    ];
  } else if (topic === "pmode-batch") {
    examples = [
      {
        title: "Batch Summary",
        caption: zh ? "計畫數、已處理數與 Yield 分開呈現。" : "Planned quantity, processed quantity, and Yield are presented separately.",
        toolbar: "BATCH SUMMARY",
        toolbarMeta: "Current Batch",
        summary: [["SITES", "8"], ["TOTAL IC", "16"], ["PROCESSED IC", "14"], ["YIELD", "92.9%"]],
      },
      {
        title: zh ? "Site 狀態" : "Site states",
        caption: zh ? "IC FAIL 與基礎設施 ERROR 必須分開解讀。" : "IC FAIL and infrastructure ERROR must be interpreted separately.",
        toolbar: "Live Site Status",
        toolbarMeta: "8 Sites",
        statusRows: [
          { label: "Site 1", value: "PASS", detail: "100%", good: true },
          { label: "Site 2", value: "FAIL", detail: "Verify" },
          { label: "Site 3", value: "ERROR", detail: "Gateway" },
        ],
      },
    ];
  } else if (topic === "emode-overview" || topic === "emode-flow") {
    examples = [
      {
        title: zh ? "指定工程目標" : "Resolve the engineering target",
        caption: zh ? "先選 Facility / PPU，再解讀 Sites 與 Job 狀態。" : "Select Facility / PPU before interpreting Sites and Job state.",
        toolbar: "Engineering Target",
        toolbarMeta: "Selected",
        summary: [["Facility", "line-1"], ["PPU", "line1-ppu-a"], ["Sites", "8"], ["Provider", "Selected"]],
      },
      {
        title: zh ? "執行 Engineering Programming" : "Run Engineering Programming",
        caption: zh ? "EMode 與 PMode 共用 Programming Job 核心欄位。" : "EMode shares the core Programming Job fields with PMode.",
        toolbar: "Programming Job",
        toolbarMeta: "BATCH READY",
        fields: [["Target IC", "Selected IC"], ["Programming Image", "firmware.bin"], ["Operations", "PROGRAM → VERIFY"], ["Selected Sites", "1, 2"]],
        primaryAction: "START PROGRAMMING",
      },
      {
        title: zh ? "查看 Site / Operator Log" : "Review Site / Operator Log",
        caption: zh ? "Engineering 模式增加 Site 診斷與完整操作紀錄。" : "Engineering mode adds Site diagnostics and full operator evidence.",
        toolbar: "Engineering Site Status",
        toolbarMeta: "REST polling",
        statusRows: [
          { label: "Site 1", value: "READY", detail: "Selected", good: true },
          { label: "Site 2", value: "PASS", detail: "Verify", good: true },
        ],
        secondaryAction: "Operator Log",
      },
    ];
  } else if (topic === "emode-programming") {
    examples = [
      {
        title: zh ? "選擇 Target 與 Sites" : "Select Target and Sites",
        caption: zh ? "Engineering targeting 明確綁定 Facility / PPU / Site。" : "Engineering targeting explicitly binds Facility / PPU / Site.",
        toolbar: "Engineering Programming",
        toolbarMeta: "Target",
        summary: [["Facility", "line-1"], ["PPU", "line1-ppu-a"], ["Selected Sites", "2"], ["Site Count", "8"]],
      },
      {
        title: zh ? "共用 Programming Job" : "Shared Programming Job",
        caption: zh ? "Target IC、Image、E/P/V/R 與 Batch Policy 使用同一套語意。" : "Target IC, Image, E/P/V/R, and Batch Policy use the same semantics.",
        toolbar: "Programming Job",
        toolbarMeta: "BATCH READY",
        fields: [["Target IC", "Selected IC"], ["Programming Image", "firmware.bin"], ["Repeat", "1"], ["Retry", "3"]],
        primaryAction: "START PROGRAMMING",
      },
      {
        title: zh ? "直接 Site 操作與 Audit" : "Direct Site action and audit",
        caption: zh ? "工程操作可針對單 Site 執行，並保留 Job / Operator Log。" : "Engineering work can target one Site while retaining Job / Operator Log evidence.",
        toolbar: "Engineering Site Status",
        toolbarMeta: "Site 1",
        statusRows: [{ label: "Site 1", value: "READY", detail: "Direct action", good: true }],
        secondaryAction: "Operator Log",
      },
    ];
  } else if (topic === "gateway-settings") {
    examples = [
      {
        title: zh ? "設定 Gateway 通訊政策" : "Configure Gateway communication policy",
        caption: zh ? "目前 UI 直接提供 Request Timeout 與 Retry Count。" : "The current UI directly exposes Request Timeout and Retry Count.",
        toolbar: "Plasma Gateway Settings",
        toolbarMeta: "Settings",
        fields: [["PPU Request Timeout", "10 sec"], ["PPU Retry Count", "3 times"]],
        primaryAction: "Apply Settings",
      },
      {
        title: zh ? "確認設定 Revision" : "Confirm the settings revision",
        caption: zh ? "新的設定套用後確認 REV；已開始的 Batch 保留 START 時凍結的 policy。" : "Confirm REV after applying changes; a started Batch keeps the policy frozen at START.",
        toolbar: "Gateway Policy",
        toolbarMeta: "Applied",
        summary: [["Request Timeout", "10 sec"], ["Retry Count", "3"], ["Revision", "REV + 1"], ["Scope", "Next Batch"]],
      },
    ];
  } else if (topic === "mock-settings") {
    examples = [
      {
        title: zh ? "設定 Mock Profile" : "Configure the Mock profile",
        caption: zh ? "Enabled、Default Image Size 與 Seed Mode 控制 Mock 測試基線。" : "Enabled, Default Image Size, and Seed Mode control the Mock test baseline.",
        toolbar: "Mock Runtime Settings",
        toolbarMeta: "Profile",
        fields: [["Enabled", "ON"], ["Default Image Size", "1024 KiB"], ["Seed Mode", "Fixed"], ["Fixed Seed", "424242"]],
        primaryAction: "Apply Settings",
      },
      {
        title: zh ? "設定 Operation 注入" : "Configure operation injection",
        caption: zh ? "各 E/P/V/R operation 可獨立設定 Error Rate 與 timing 參數。" : "Each E/P/V/R operation can independently configure Error Rate and timing parameters.",
        toolbar: "Operation Profile",
        toolbarMeta: "E / P / V / R",
        fields: [["Error Rate", "0.0%"], ["Base Time", "100 ms"], ["Throughput", "1024 KiB/s"], ["Jitter", "0 ms"]],
        primaryAction: "Apply Settings",
      },
    ];
  }

  return (
    <aside className="documentExampleRail" aria-label={zh ? "操作畫面示例" : "Operation screen examples"}>
      <header className="documentExampleRailHeader">
        <span className="documentExampleRailIcon" aria-hidden="true">▣</span>
        <div>
          <small>{zh ? "操作畫面示例" : "OPERATION SCREEN EXAMPLES"}</small>
          <h2>{zh ? "操作畫面示例" : "Operation screen examples"}</h2>
          <p>{zh ? "以下畫面用來對照左側說明；屬於文件示意，不是即時系統狀態。" : "These screens illustrate the documentation at left; they are examples, not live system state."}</p>
        </div>
      </header>
      {examples.map((example, index) => (
        <section className="documentOperationExample" data-doc-example={`${topic}-${index + 1}`} key={`${topic}-${example.title}`}>
          <header><span>{index + 1}</span><div><strong>{example.title}</strong><p>{example.caption}</p></div></header>
          <div className="documentMockScreen">
            <div className="documentMockToolbar"><b>{example.toolbar}</b><span>{example.toolbarMeta}</span></div>
            {example.statusRows?.map(row => (
              <div className="documentMockStatusRow" key={`${row.label}-${row.value}`}>
                <b>{row.label}</b><span data-tone={row.good ? "good" : undefined}>{row.value}</span>{row.detail ? <span>{row.detail}</span> : null}
              </div>
            ))}
            {example.fields ? (
              <div className="documentMockForm">
                {example.fields.map(([label, value]) => <label key={label}><span>{label}</span><b>{value}</b></label>)}
                {(example.secondaryAction || example.primaryAction) ? (
                  <div className="documentMockActions">
                    {example.secondaryAction ? <span>{example.secondaryAction}</span> : null}
                    {example.primaryAction ? <strong>{example.primaryAction}</strong> : null}
                  </div>
                ) : null}
              </div>
            ) : null}
            {example.summary ? (
              <div className="documentMockSummary">
                {example.summary.map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}
              </div>
            ) : null}
            {!example.fields && (example.secondaryAction || example.primaryAction) ? (
              <div className="documentMockForm"><div className="documentMockActions">
                {example.secondaryAction ? <span>{example.secondaryAction}</span> : null}
                {example.primaryAction ? <strong>{example.primaryAction}</strong> : null}
              </div></div>
            ) : null}
          </div>
        </section>
      ))}
    </aside>
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
          <p>{zh ? "以下 1–7 對應左側 7 個大步驟；這些是操作畫面示意，不是即時系統狀態。" : "Examples 1–7 correspond to the seven major steps at left. These are illustrative operation screens, not live system state."}</p>
        </div>
      </header>

      <section className="documentOperationExample" data-step="1">
        <header><span>1</span><div><strong>{zh ? "新增 PPU 連線" : "Add a PPU connection"}</strong><p>PPU → Registration → + Add PPU Connection</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 1：新增 PPU 連線操作畫面示例" : "Step 1 illustrative add PPU connection screen"}>
          <div className="documentMockToolbar"><b>Registration</b><span>+ Add PPU Connection</span></div>
          <div className="documentMockForm">
            <label><span>Console Alias</span><b>line1-ppu-a</b></label>
            <label><span>Plasma Gateway Endpoint</span><b>http://192.168.10.21:18080</b></label>
            <div className="documentMockActions"><span>Cancel</span><strong>Add Connection</strong></div>
          </div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="2">
        <header><span>2</span><div><strong>{zh ? "確認 PPU 狀態" : "Confirm PPU state"}</strong><p>{zh ? "註冊前確認 Connectivity、Health 與 Registration readiness。" : "Before Registration, confirm Connectivity, Health, and Registration readiness."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 2：PPU 狀態操作畫面示例" : "Step 2 illustrative PPU state screen"}>
          <div className="documentMockToolbar"><b>Known PPU Connections</b><span>Refresh</span></div>
          <div className="documentMockStatusRow"><b>line1-ppu-a</b><span data-tone="good">Online</span><span data-tone="good">Healthy</span></div>
          <div className="documentMockSummary">
            <div><small>PPU ID</small><strong>ppu-8f2c9d7e</strong></div>
            <div><small>Registration</small><strong>Not Registered</strong></div>
            <div><small>Execution</small><strong>Ready</strong></div>
            <div><small>Reported Sites</small><strong>8</strong></div>
          </div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="3">
        <header><span>3</span><div><strong>{zh ? "註冊燒錄權限" : "Register programming admission"}</strong><p>{zh ? "Readiness 全部通過後執行 Validate & Register for Programming。" : "After all readiness checks pass, run Validate & Register for Programming."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 3：Programming Registration 操作畫面示例" : "Step 3 illustrative programming registration screen"}>
          <div className="documentMockToolbar"><b>Registration Readiness</b><span>Ready</span></div>
          <div className="documentMockSummary">
            <div><small>Observation</small><strong>Current</strong></div>
            <div><small>Transport</small><strong>Online</strong></div>
            <div><small>Execution</small><strong>Ready</strong></div>
            <div><small>Identity Conflict</small><strong>None</strong></div>
          </div>
          <div className="documentMockForm">
            <div className="documentMockActions"><strong>Validate &amp; Register for Programming</strong></div>
          </div>
          <div className="documentMockStatusRow"><b>Programming Registration</b><span data-tone="good">Registered</span><span>Commissioned</span></div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="4">
        <header><span>4</span><div><strong>{zh ? "選擇受管操作 PPU" : "Select the Managed Operations PPU"}</strong><p>{zh ? "將已 Registered 的 PPU 指定為目前 managed workflow 目標。" : "Select a Registered PPU as the current managed-workflow target."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 4：Managed Operations PPU 操作畫面示例" : "Step 4 illustrative Managed Operations PPU screen"}>
          <div className="documentMockToolbar"><b>Known PPU Connections</b><span>Registered</span></div>
          <div className="documentMockSummary">
            <div><small>Console Alias</small><strong>line1-ppu-a</strong></div>
            <div><small>Facility</small><strong>line-1</strong></div>
            <div><small>Connectivity</small><strong>Online</strong></div>
            <div><small>Health</small><strong>Healthy</strong></div>
          </div>
          <div className="documentMockForm">
            <div className="documentMockActions"><strong>Use for Managed Operations</strong></div>
          </div>
          <div className="documentMockStatusRow"><b>Managed Operations PPU</b><span data-tone="good">Selected</span><span>line1-ppu-a</span></div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="5">
        <header><span>5</span><div><strong>{zh ? "設定 PPU 網路" : "Configure the PPU network"}</strong><p>{zh ? "查看 Desired Network，必要時進入 Configure Network。" : "Review Desired Network and open Configure Network when a change is required."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 5：PPU Network Configuration 操作畫面示例" : "Step 5 illustrative PPU Network Configuration screen"}>
          <div className="documentMockToolbar"><b>PPU Network Configuration</b><span>Configure Network</span></div>
          <div className="documentMockSummary">
            <div><small>Interface</small><strong>eth0</strong></div>
            <div><small>Desired Mode</small><strong>DHCP</strong></div>
            <div><small>Activation</small><strong>Not Supported</strong></div>
            <div><small>Revision</small><strong>1</strong></div>
          </div>
          <div className="documentMockForm">
            <label><span>Desired Mode</span><b>Static IPv4</b></label>
            <label><span>IPv4 Address / Prefix</span><b>192.168.10.21 / 24</b></label>
            <label><span>Default Gateway</span><b>192.168.10.1</b></label>
            <label><span>DNS Servers</span><b>192.168.10.1</b></label>
            <div className="documentMockActions"><span>Cancel</span><strong>Save Desired Network</strong></div>
          </div>
          <div className="documentMockStatusRow"><b>Activation capability</b><span>Not Supported</span><span>{zh ? "不是 Fault" : "Not a fault"}</span></div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="6">
        <header><span>6</span><div><strong>{zh ? "Platform 維護" : "Maintain the Platform"}</strong><p>{zh ? "使用獨立的 Platform Maintenance 授權更新 Platform Release / Runtime。" : "Use the separate Platform Maintenance authorization to update Platform Release / Runtime."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 6：Platform Maintenance 操作畫面示例" : "Step 6 illustrative Platform Maintenance screen"}>
          <div className="documentMockToolbar"><b>Platform Maintenance</b><span>Bootstrap Supported</span></div>
          <div className="documentMockForm">
            <label><span>Pairing Token</span><b>••••••••••••</b></label>
            <div className="documentMockActions"><strong>Authorize Platform Maintenance</strong></div>
            <label><span>Platform Release Package</span><b>plasma-z2-ps-kit-0.2.1-…tar.gz</b></label>
            <label><span>SHA-256 Sidecar</span><b>SHA256SUMS</b></label>
            <div className="documentMockActions"><strong>Update PPU Platform Release</strong></div>
          </div>
          <div className="documentMockSummary">
            <div><small>Authorization</small><strong>Authorized</strong></div>
            <div><small>Runtime</small><strong>Active</strong></div>
            <div><small>Platform Release</small><strong>0.2.1</strong></div>
            <div><small>PS Loop</small><strong>Available</strong></div>
          </div>
          <div className="documentMockForm">
            <div className="documentMockActions"><span>Run PS Loop Test</span></div>
          </div>
        </div>
      </section>

      <section className="documentOperationExample" data-step="7">
        <header><span>7</span><div><strong>{zh ? "Site 設定與 Runtime 就緒" : "Configure Sites and confirm Runtime readiness"}</strong><p>{zh ? "保存 Site Desired Configuration，必要時再 Activate Desired Configuration。" : "Save Site Desired Configuration, then Activate Desired Configuration when required."}</p></div></header>
        <div className="documentMockScreen" aria-label={zh ? "步驟 7：Site Configuration 與 Runtime Activation 操作畫面示例" : "Step 7 illustrative Site Configuration and Runtime Activation screen"}>
          <div className="documentMockToolbar"><b>Sites</b><span>8 Reported</span></div>
          <div className="documentMockStatusRow"><b>Site 1</b><span data-tone="good">Ready</span><span>Enabled</span></div>
          <div className="documentMockForm">
            <label><span>Desired Enabled</span><b>True</b></label>
            <label><span>Desired Interface</span><b>fpga</b></label>
            <label><span>Desired Target</span><b>target-profile-a</b></label>
            <div className="documentMockActions"><span>Discard Draft</span><strong>Save Desired Configuration</strong></div>
          </div>
          <div className="documentMockSummary">
            <div><small>Draft</small><strong>Saved</strong></div>
            <div><small>Desired</small><strong>Current</strong></div>
            <div><small>Runtime</small><strong>Reconciled</strong></div>
            <div><small>Active Execution</small><strong>None</strong></div>
          </div>
          <div className="documentMockForm">
            <div className="documentMockActions"><strong>Activate Desired Configuration</strong></div>
          </div>
          <div className="documentMockStatusRow"><b>Configuration lifecycle</b><span>Draft → Desired</span><span data-tone="good">→ Runtime</span></div>
        </div>
      </section>
    </aside>
  );
}

function TopicContent({ topic, zh }: { topic: Topic; zh: boolean }) {
  if (topic === "pmode-overview") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Facility", "產線、實驗室或管理區域"],
      ["PPU", "實際執行燒錄工作的設備"],
      ["Site", "可獨立執行的燒錄位置"],
      ["Programming Job", "Target / Image / Operations / Policy"],
      ["Batch", "START 後由 Server 擁有的執行實例"],
    ] : [
      ["Facility", "Line, lab, or managed area"],
      ["PPU", "Equipment that executes programming"],
      ["Site", "Independently executable programming position"],
      ["Programming Job", "Target / Image / Operations / Policy"],
      ["Batch", "Server-owned execution instance after START"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">PMODE · PRODUCTION OPERATION</p>
          <h1>{zh ? "PMode 操作總覽" : "PMode Overview"}</h1>
          <p className="documentLead">{zh ? "PMode 是 Production Mode（量產模式），用於正式燒錄與批次量產作業。先理解 Facility / PPU / Site、Programming Job 與 Batch 的關係，再進入實際操作。" : "PMode means Production Mode. It is used for production programming and batch operations. Understand Facility / PPU / Site, Programming Job, and Batch ownership before operating the production flow."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "PMode 核心模型　5 個主要物件" : "PMode core model · 5 primary objects"}
          subtitle={zh ? "量產操作不是單一畫面，而是一組明確的設備、工作與執行 ownership。" : "Production operation is a set of explicit equipment, work-definition, and execution-ownership concepts."}
          steps={overviewSteps}
        />

        <DocumentCallout tone="info" label={zh ? "操作原則" : "Operating principle"}>
          <p>{zh ? "Operator 先選定 Facility / PPU / Site，再以單一 Programming Job 定義 Target IC、Programming Image、E/P/V/R 與 Batch Policy。" : "The operator first selects Facility / PPU / Site, then defines Target IC, Programming Image, E/P/V/R, and Batch Policy in one Programming Job."}</p>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "核心物件" : "Core objects"} summary={zh ? "先建立 PMode 的 object model，避免把 UI、設備與 Batch 混在一起。" : "Establish the PMode object model before interpreting UI, equipment, and Batch state."} />
              <DocumentDataTable
                headers={[zh ? "物件" : "Object", zh ? "用途" : "Purpose"]}
                rows={[
                  ["Facility", zh ? "設備所在的產線、實驗室或管理區域。" : "The line, lab, or managed area that owns PPUs."],
                  ["PPU", zh ? "實際執行燒錄工作的 PPU。" : "The PPU that executes programming work."],
                  ["Site", zh ? "PPU 上可獨立執行工作的實體燒錄位置。" : "An independently executable programming position on a PPU."],
                  ["Programming Job", zh ? "Target IC、Image、Operations 與 Batch Policy 的工作定義。" : "The work definition containing Target IC, Image, Operations, and Batch Policy."],
                  ["Batch", zh ? "START 後由 Server 擁有與追蹤的執行實例。" : "The server-owned execution instance created after START."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Authority boundary" : "Authority boundary"} summary={zh ? "畫面顯示狀態，但 backend 才是 execution 與結果 truth source。" : "The UI presents state, while backend ownership remains authoritative for execution and results."} />
              <DocumentCallout tone="warning" label={zh ? "UI ≠ execution owner" : "UI ≠ execution owner"}>
                <p>{zh ? "PMode UI 是操作介面；真正的 PPU execution ownership、Batch state 與結果判定仍以 backend 為準。" : "The PMode UI is an operator surface. Backend PPU execution ownership, Batch state, and result truth remain authoritative."}</p>
              </DocumentCallout>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "pmode-flow") {
    const flowSteps: Array<[string, string]> = zh ? [
      ["選擇設備範圍", "Facility / PPU / Site"],
      ["選擇 Target IC", "指定目標 IC"],
      ["選擇 Programming Image", "指定燒錄映像"],
      ["選擇 Operations", "Erase / Program / Verify / Read"],
      ["設定 Batch Policy", "Repeat / Retry / Stop Policy"],
      ["確認 BATCH READY", "所有 readiness gate 通過"],
      ["START PROGRAMMING", "建立 server-owned Batch"],
      ["監看執行", "Live Site Status / Logs"],
      ["確認結果", "Batch Summary"],
    ] : [
      ["Select equipment scope", "Facility / PPU / Site"],
      ["Select Target IC", "Choose the IC target"],
      ["Select Programming Image", "Choose the programming image"],
      ["Choose Operations", "Erase / Program / Verify / Read"],
      ["Set Batch Policy", "Repeat / Retry / Stop Policy"],
      ["Confirm BATCH READY", "All readiness gates pass"],
      ["START PROGRAMMING", "Create the server-owned Batch"],
      ["Monitor execution", "Live Site Status / Logs"],
      ["Review results", "Batch Summary"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">PMODE · OPERATION FLOW</p>
          <h1>{zh ? "PMode 操作流程" : "PMode Operation Flow"}</h1>
          <p className="documentLead">{zh ? "量產流程從 Production Set、Programming Job、readiness，到 server-owned Batch 與結果確認依序推進。START 是 ownership 的分界點。" : "The production flow progresses from Production Set and Programming Job through readiness, server-owned Batch execution, and result review. START is the ownership boundary."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "量產流程　共 9 個步驟" : "Production flow · 9 steps"}
          subtitle={zh ? "先看完整流程，再依序執行；START 後不要再把 UI selection 當作正在執行的 Batch membership。" : "Review the whole sequence first. After START, do not treat UI selection as the membership of the running Batch."}
          steps={flowSteps}
        />

        <DocumentCallout tone="warning" label={zh ? "START 後 membership 凍結" : "Membership freezes after START"}>
          <p>{zh ? "START 後 Batch membership 凍結，不能用切換模式或重新選 Site 來改變正在執行的 Batch。" : "Batch membership is frozen after START and cannot be changed by switching modes or reselecting Sites."}</p>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "準備 Production Set" : "Prepare the Production Set"} summary={zh ? "先決定設備範圍，再定義工作。" : "Resolve the equipment scope before defining work."} />
              <div className="documentCompactProcedure">
                {(zh ? ["選擇 Facility / PPU / Site", "確認至少一個可執行 Site", "確認設備不是被其他 active execution owner 佔用"] : ["Select Facility / PPU / Site", "Confirm at least one executable Site", "Confirm the equipment is not owned by another active execution"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "定義 Programming Job" : "Define the Programming Job"} summary={zh ? "Target、Image、Operations 與 Batch Policy 共同形成本次工作。" : "Target, Image, Operations, and Batch Policy define the work."} />
              <div className="documentCompactProcedure">
                {(zh ? ["選擇 Target IC", "選擇 Programming Image", "勾選 E/P/V/R", "設定 Repeat / Retry / Stop Policy", "確認 BATCH READY"] : ["Select Target IC", "Select Programming Image", "Choose E/P/V/R", "Set Repeat / Retry / Stop Policy", "Confirm BATCH READY"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={3} title={zh ? "執行與監看" : "Execute and monitor"} summary={zh ? "START 後由 server-owned Batch 管理執行生命週期。" : "After START, the server-owned Batch manages the execution lifecycle."} />
              <div className="documentCompactProcedure">
                {(zh ? ["按 START PROGRAMMING", "監看 Live Site Status", "必要時使用 whole-Batch ABORT", "確認 Batch Summary 與 terminal state"] : ["Select START PROGRAMMING", "Monitor Live Site Status", "Use whole-Batch ABORT when required", "Review Batch Summary and terminal state"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
              <DocumentCallout tone="info" label={zh ? "Execution ownership" : "Execution ownership"}>
                <ul>
                  <li>{zh ? "執行中以 whole-Batch ABORT 作為主要停止操作。" : "Whole-Batch ABORT is the primary runtime stop action."}</li>
                  <li>{zh ? "同一 PPU 同時間最多只有一個 active execution owner。" : "A PPU has at most one active execution owner at a time."}</li>
                </ul>
              </DocumentCallout>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "pmode-programming") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Target", "選擇 Target IC"],
      ["Image", "選擇 Programming Image"],
      ["Operations", "Erase / Program / Verify / Read"],
      ["Batch Policy", "Repeat / Retry / Stop Policy"],
    ] : [
      ["Target", "Select Target IC"],
      ["Image", "Select Programming Image"],
      ["Operations", "Erase / Program / Verify / Read"],
      ["Batch Policy", "Repeat / Retry / Stop Policy"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">PMODE · PROGRAMMING JOB</p>
          <h1>{zh ? "Programming Job 設定" : "Programming Job Settings"}</h1>
          <p className="documentLead">{zh ? "Programming Job 把 Target、Image、Operations 與 Batch Policy 集中成單一工作定義。量產開始前，這些欄位必須共同形成可執行的 BATCH READY 狀態。" : "Programming Job combines Target, Image, Operations, and Batch Policy into one work definition. Before production starts, these fields must collectively produce a BATCH READY state."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "Programming Job　4 個設定群組" : "Programming Job · 4 configuration groups"}
          subtitle={zh ? "先確定 target 與 image，再選 operations，最後定義 batch policy。" : "Resolve target and image first, choose operations next, then define Batch policy."}
          steps={overviewSteps}
        />

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "Target 與 Image" : "Target and Image"} summary={zh ? "Program / Verify 必須有可用的目標與 Programming Image。" : "Program / Verify require a usable target and Programming Image."} />
              <DocumentDataTable
                headers={[zh ? "欄位" : "Field", zh ? "說明" : "Description"]}
                rows={[
                  ["Target IC", zh ? "本次工作要操作的 IC。真實 provider 執行時必須能對應到受支援的 target。" : "The IC target for this work. Real-provider execution must resolve to a supported target."],
                  ["Programming Image", zh ? "要寫入或驗證的 Programming Image。Program / Verify 需要有效 Image。" : "The Programming Image used for Program / Verify operations."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Operations" : "Operations"} summary={zh ? "每個 operation 都有獨立語意，不應把結果混成單一 PASS/FAIL 前置假設。" : "Each operation has distinct semantics and should not be collapsed into a single pre-assumed PASS/FAIL meaning."} />
              <DocumentDataTable
                headers={[zh ? "Operation" : "Operation", zh ? "作用" : "Purpose"]}
                rows={[
                  ["Erase", zh ? "擦除目標可程式化儲存區。" : "Erase the target programmable storage."],
                  ["Program", zh ? "把 Programming Image 寫入目標。" : "Write the Programming Image to the target."],
                  ["Verify", zh ? "比對目標內容與 Programming Image。" : "Compare target content with the Programming Image."],
                  ["Read", zh ? "讀回 target-defined Main Flash 或對應可讀區域。" : "Read back the target-defined Main Flash or readable region."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={3} title={zh ? "Batch Policy" : "Batch Policy"} summary={zh ? "Batch Policy 決定計畫處理次數、Site retry 與停止條件。" : "Batch Policy defines planned processing count, Site retry, and stop conditions."} />
              <DocumentDataTable
                headers={[zh ? "欄位" : "Field", zh ? "說明" : "Description"]}
                rows={[
                  ["Repeat", zh ? "每個已選 Site 預計處理的 IC 次數。Mock 可模擬多顆 IC；真實硬體仍需要實體換料/交接機制。" : "Planned IC count per selected Site. Mock can simulate repeats; real hardware still requires physical device handoff."],
                  ["Site Retry Limit", zh ? "可信任的單 Site 操作失敗後允許的 Job retry 次數；不是 Gateway 通訊 retry。" : "Job retry count after a trusted Site operation failure; it is not Gateway communication retry."],
                  ["Stop Policy", zh ? "當 retry-exhausted FAULTED Sites 達條件時，決定是否停止後續 Batch 工作。" : "Determines when retry-exhausted FAULTED Sites stop subsequent Batch work."],
                ]}
              />
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "pmode-batch") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Batch Summary", "設備範圍、計畫數與結果 KPI"],
      ["Site State", "READY / RUNNING / PASS / FAIL / ERROR"],
      ["Evidence Boundary", "IC FAIL 與 Infrastructure ERROR 分離"],
    ] : [
      ["Batch Summary", "Scope, planned quantity, and result KPIs"],
      ["Site State", "READY / RUNNING / PASS / FAIL / ERROR"],
      ["Evidence Boundary", "Separate IC FAIL from Infrastructure ERROR"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">PMODE · BATCH & STATUS</p>
          <h1>{zh ? "Batch 指標與狀態" : "Batch Metrics and Status"}</h1>
          <p className="documentLead">{zh ? "Batch Summary 與 Site 狀態是量產執行的主要觀察面。計畫數、已處理數、IC 結果與 infrastructure error 必須分開解讀。" : "Batch Summary and Site states are the main production-observation surfaces. Planned quantity, processed quantity, IC results, and infrastructure errors must remain separate."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "結果判讀　3 個層次" : "Result interpretation · 3 layers"}
          subtitle={zh ? "先看 Batch KPI，再看 Site terminal state，最後確認失敗屬於 IC 還是基礎設施。" : "Review Batch KPIs first, Site terminal state second, then determine whether a failure belongs to the IC or infrastructure."}
          steps={overviewSteps}
        />

        <DocumentCallout tone="critical" label="IC FAIL ≠ Infrastructure ERROR">
          <p>{zh ? "Gateway、PPU 通訊或 runtime 基礎設施異常不能算成 IC FAIL。" : "Gateway, PPU communication, or runtime infrastructure failures must not be counted as IC FAIL."}</p>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title="Batch Summary" summary={zh ? "KPI 必須區分 equipment scope、planned quantity 與 processed outcomes。" : "KPIs separate equipment scope, planned quantity, and processed outcomes."} />
              <DocumentDataTable
                headers={[zh ? "指標" : "Metric", zh ? "定義" : "Definition"]}
                rows={[
                  ["SITES", zh ? "START 時凍結的已選 Site 數。" : "Selected Site count frozen at START."],
                  ["TOTAL IC", zh ? "SITES × Repeat，代表計畫處理數。" : "SITES × Repeat, the planned IC quantity."],
                  ["PROCESSED IC", zh ? "PASS + FAIL；基礎設施 ERROR 不計入。" : "PASS + FAIL; infrastructure ERROR is excluded."],
                  ["PASS", zh ? "完整計畫 round 成功的 IC 數。" : "IC count with a successful complete round."],
                  ["FAIL", zh ? "具有可信任 DUT / Site 失敗證據的 IC 數。" : "IC count with trusted DUT / Site failure evidence."],
                  ["YIELD", zh ? "PASS / (PASS + FAIL)。沒有可信任結果時顯示 —。" : "PASS / (PASS + FAIL). Shows — before trusted results exist."],
                  ["BATCH TIME", zh ? "Batch 從開始到現在或 terminal 的經過時間。" : "Elapsed Batch time until now or terminal state."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Site 狀態" : "Site states"} summary={zh ? "Site state 表示執行位置的 lifecycle 與 terminal result。" : "Site state represents execution-position lifecycle and terminal result."} />
              <DocumentDataTable
                headers={[zh ? "狀態" : "State", zh ? "意義" : "Meaning"]}
                rows={[
                  ["READY", zh ? "可加入下一個 Batch。" : "Available for the next Batch."],
                  ["RUNNING", zh ? "已接受 Job 尚未 terminal。" : "An accepted Job is still active."],
                  ["PASS / SUCCESS", zh ? "計畫工作完成且成功。" : "Planned work completed successfully."],
                  ["FAIL / FAULTED", zh ? "可信任的 DUT / Site 燒錄失敗。" : "Trusted DUT / Site programming failure."],
                  ["ERROR", zh ? "Gateway、PPU 通訊或 runtime 基礎設施異常；不是 IC FAIL。" : "Gateway, PPU communication, or runtime infrastructure failure; not an IC FAIL."],
                  ["STOPPED", zh ? "因 stop policy 或相關基礎設施條件未繼續。" : "Execution did not continue because of stop policy or infrastructure conditions."],
                  ["CANCELLED", zh ? "Operator ABORT / cancel 已完成。" : "Operator ABORT / cancel completed."],
                ]}
              />
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "emode-overview") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Targeting", "Facility / PPU / Site"],
      ["Programming", "共用 Programming Job 語意"],
      ["Diagnostics", "Site / Job / Operator Log"],
      ["Settings", "Gateway / Mock"],
    ] : [
      ["Targeting", "Facility / PPU / Site"],
      ["Programming", "Shared Programming Job semantics"],
      ["Diagnostics", "Site / Job / Operator Log"],
      ["Settings", "Gateway / Mock"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">EMODE · ENGINEERING OPERATION</p>
          <h1>{zh ? "EMode 操作總覽" : "EMode Overview"}</h1>
          <p className="documentLead">{zh ? "EMode 是 Engineering Mode（工程模式），用於工程開發、驗證、診斷與設定。它保留與 PMode 共用的 Programming Job 語意，但增加工程 targeting、單 Site 操作、診斷資訊、Gateway 與 Mock 設定。" : "EMode means Engineering Mode. It is used for engineering development, validation, diagnostics, and configuration while sharing Programming Job semantics with PMode and adding engineering targeting, direct Site actions, Gateway, and Mock settings."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "EMode　4 個主要能力" : "EMode · 4 primary capabilities"}
          subtitle={zh ? "Engineering mode 的差異在 targeting、診斷與直接操作，不是另一套 Programming Job 定義。" : "Engineering mode differs in targeting, diagnostics, and direct operations, not in creating a second Programming Job definition."}
          steps={overviewSteps}
        />

        <DocumentCallout tone="info" label={zh ? "共用核心語意" : "Shared core semantics"}>
          <p>{zh ? "PMode 與 EMode 的 Target IC、Programming Image、Operations 與 Batch Policy 使用同一套 operational concept。" : "PMode and EMode use the same operational concepts for Target IC, Programming Image, Operations, and Batch Policy."}</p>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "使用順序" : "Operating order"} summary={zh ? "先解析 target，再讀 Sites 與 logs。" : "Resolve the target before interpreting Sites and logs."} />
              <div className="documentCompactProcedure">
                {(zh ? ["選擇 Facility", "選擇 PPU", "確認 Site 狀態", "定義 Programming Job", "執行 Batch 或單 Site 操作", "查看 Site / Job / Operator Log"] : ["Select Facility", "Select PPU", "Confirm Site state", "Define the Programming Job", "Run Batch or direct Site operation", "Review Site / Job / Operator Log"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Engineering ownership" : "Engineering ownership"} summary={zh ? "診斷資訊較多，但不能繞過 backend ownership。" : "Engineering exposes more diagnostics but does not bypass backend ownership."} />
              <ul>
                <li>{zh ? "Direct single-Site Job 與 server-owned Batch 是不同 execution owner。" : "Direct single-Site Jobs and server-owned Batches are different execution owners."}</li>
                <li>{zh ? "EMode 提供更多診斷資訊，但不能繞過 backend 的 PPU ownership 與授權。" : "Engineering diagnostics do not bypass backend PPU ownership or authorization."}</li>
              </ul>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
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
                  "Enter the Platform Maintenance Pairing Token and select Authorize Platform Maintenance",
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
              <div className="documentSubsection">
                <h3><span>7.4</span>{zh ? "初次設定路徑" : "First-time setup paths"}</h3>
                <p>{zh ? "依 PPU 目前是否已安裝 Runtime，初次設定有兩條常見路徑；兩者最後都必須回到相同的 Registration、Site 與 Programming readiness 判定。" : "First-time setup normally follows one of two paths depending on whether Runtime is already installed. Both paths converge on the same Registration, Site, and Programming readiness gates."}</p>
                <h4>{zh ? "已有 Runtime 的 PPU" : "Runtime-present PPU"}</h4>
                <div className="documentCompactProcedure">
                  {(zh ? [
                    "確認 PPU 網路可達並 Add PPU Connection",
                    "確認 PPU ID / Connectivity / Health",
                    "Validate & Register for Programming",
                    "Use for Managed Operations",
                    "視需要設定 Network 與 Site Desired Configuration",
                    "必要時執行 Runtime Activation，最後進入 Programming 驗證",
                  ] : [
                    "Confirm PPU network reachability and Add PPU Connection",
                    "Confirm PPU ID / Connectivity / Health",
                    "Validate & Register for Programming",
                    "Use for Managed Operations",
                    "Configure Network and Site Desired Configuration when needed",
                    "Run Runtime Activation when needed, then proceed to Programming validation",
                  ]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
                </div>
                <h4>{zh ? "Bootstrap-only PPU" : "Bootstrap-only PPU"}</h4>
                <div className="documentCompactProcedure">
                  {(zh ? [
                    "完成 Bootstrap factory provisioning 並 Add PPU Connection",
                    "進入 Platform 並 Authorize Platform Maintenance",
                    "部署 PPU Platform Release / Runtime，確認 Runtime Active",
                    "回到 Registration，Validate & Register for Programming",
                    "設定 Sites，必要時執行 Runtime Activation",
                    "完成 Programming qualification",
                  ] : [
                    "Complete Bootstrap factory provisioning and Add PPU Connection",
                    "Open Platform and Authorize Platform Maintenance",
                    "Deploy the PPU Platform Release / Runtime and confirm Runtime Active",
                    "Return to Registration and Validate & Register for Programming",
                    "Configure Sites and run Runtime Activation when needed",
                    "Complete Programming qualification",
                  ]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
                </div>
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
    const flowSteps: Array<[string, string]> = zh ? [
      ["選擇 Facility", "定位工程區域"],
      ["選擇 PPU", "指定工程目標"],
      ["確認 Site 狀態", "確認可執行性"],
      ["選擇 Target / Image", "定義燒錄內容"],
      ["選擇 E/P/V/R", "定義操作"],
      ["執行工作", "Batch 或單 Site"],
      ["監看 Logs", "Site / Job / Operator"],
      ["Retry / Cancel / Diagnose", "依結果處置"],
    ] : [
      ["Select Facility", "Resolve the engineering area"],
      ["Select PPU", "Choose the engineering target"],
      ["Confirm Site state", "Verify executability"],
      ["Select Target / Image", "Define programming content"],
      ["Choose E/P/V/R", "Define operations"],
      ["Run work", "Batch or direct Site"],
      ["Monitor Logs", "Site / Job / Operator"],
      ["Retry / Cancel / Diagnose", "Respond to the result"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">EMODE · OPERATION FLOW</p>
          <h1>{zh ? "EMode 操作流程" : "EMode Operation Flow"}</h1>
          <p className="documentLead">{zh ? "EMode 流程從工程 target resolution 開始，再進入 Programming Job、Batch 或單 Site 操作，最後以 Site / Job / Operator Log 完成診斷。" : "The EMode flow starts with engineering target resolution, proceeds through Programming Job and Batch or direct Site work, then closes the loop with Site / Job / Operator Log diagnostics."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "工程操作流程　共 8 個步驟" : "Engineering flow · 8 steps"}
          subtitle={zh ? "工程模式增加診斷與 direct Site action，但 execution ownership 仍需明確。" : "Engineering adds diagnostics and direct Site actions, while execution ownership remains explicit."}
          steps={flowSteps}
        />

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "Resolve target" : "Resolve target"} summary={zh ? "Facility / PPU / Site 是所有後續狀態的上下文。" : "Facility / PPU / Site provide the context for every later state."} />
              <div className="documentCompactProcedure">
                {(zh ? ["選 Facility", "選 PPU", "確認 Site enabled / state", "確認 selected Sites"] : ["Select Facility", "Select PPU", "Confirm Site enabled / state", "Confirm selected Sites"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Define and run work" : "Define and run work"} summary={zh ? "共用 Programming Job 定義，依需求選 Batch 或 direct Site action。" : "Use the shared Programming Job definition, then choose Batch or direct Site action as needed."} />
              <div className="documentCompactProcedure">
                {(zh ? ["選 Target IC / Programming Image", "選 E/P/V/R", "設定 Batch Policy（若使用 Batch）", "執行 START PROGRAMMING 或單 Site 操作"] : ["Select Target IC / Programming Image", "Choose E/P/V/R", "Set Batch Policy when using Batch", "Run START PROGRAMMING or a direct Site action"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={3} title={zh ? "Observe and diagnose" : "Observe and diagnose"} summary={zh ? "工程判讀應同時查看 Site、Job 與 Operator Log。" : "Engineering interpretation should use Site, Job, and Operator Log together."} />
              <div className="documentCompactProcedure">
                {(zh ? ["查看 Site state / progress", "查看 Job result", "查看 Operator Log", "必要時 Retry / Cancel / Diagnose"] : ["Review Site state / progress", "Review Job result", "Review Operator Log", "Retry / Cancel / Diagnose when required"]).map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}
              </div>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "emode-programming") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Targeting", "Facility / PPU / Site"],
      ["Programming Job", "Target / Image / E/P/V/R"],
      ["Execution", "Batch 或 direct Site"],
      ["Evidence", "Site / Job / Operator Log"],
    ] : [
      ["Targeting", "Facility / PPU / Site"],
      ["Programming Job", "Target / Image / E/P/V/R"],
      ["Execution", "Batch or direct Site"],
      ["Evidence", "Site / Job / Operator Log"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">EMODE · PROGRAMMING</p>
          <h1>EMode Programming</h1>
          <p className="documentLead">{zh ? "Programming Job 的 Target IC、Programming Image、Operations、Batch Policy 與 PMode 共用相同概念。EMode 額外提供工程 targeting、Site diagnostic table、直接單 Site 操作與完整 audit log。" : "Programming Job fields share the same concepts as PMode. EMode adds engineering targeting, a diagnostic Site table, direct single-Site actions, and full audit evidence."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "EMode Programming　4 個組成" : "EMode Programming · 4 components"}
          subtitle={zh ? "工程模式的價值在 target precision、direct action 與 evidence，不是複製另一套 Programming Job。" : "Engineering value comes from target precision, direct action, and evidence, not from duplicating Programming Job semantics."}
          steps={overviewSteps}
        />

        <DocumentCallout tone="info" label={zh ? "同一 operational concept 採相同規則" : "One operational concept, one rule set"}>
          <p>{zh ? "EMode 的差異主要是工程診斷與直接操作，不是另一套 Programming Job 定義。" : "EMode differs mainly in diagnostics and direct operations, not in defining a second Programming Job model."}</p>
        </DocumentCallout>

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "Engineering targeting" : "Engineering targeting"} summary={zh ? "所有工作都先綁定明確的 Facility / PPU / Site context。" : "Every work item starts with explicit Facility / PPU / Site context."} />
              <DocumentDataTable
                headers={[zh ? "層級" : "Scope", zh ? "作用" : "Purpose"]}
                rows={[
                  ["Facility", zh ? "工程操作所在的管理區域。" : "Managed area for engineering work."],
                  ["PPU", zh ? "實際執行工作的目標 PPU。" : "Target PPU that performs the work."],
                  ["Site", zh ? "可選為 Batch member 或 direct action target 的執行位置。" : "Execution position selectable for Batch membership or direct action."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title="Programming Job" summary={zh ? "Target IC、Image、Operations 與 Batch Policy 與 PMode 共用。" : "Target IC, Image, Operations, and Batch Policy are shared with PMode."} />
              <DocumentDataTable
                headers={[zh ? "群組" : "Group", zh ? "內容" : "Content"]}
                rows={[
                  ["Target", "Target IC"],
                  ["Image", "Programming Image"],
                  ["Operations", "Erase / Program / Verify / Read"],
                  ["Batch Policy", "Repeat / Retry / Stop Policy"],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={3} title={zh ? "Execution 與 evidence" : "Execution and evidence"} summary={zh ? "Batch 與 direct Site action 有不同 ownership；結果要回到 logs 與 Site state 判讀。" : "Batch and direct Site actions have different ownership; interpret results through logs and Site state."} />
              <ul>
                <li>{zh ? "Direct single-Site Job 與 server-owned Batch 是不同 execution owner。" : "Direct single-Site Jobs and server-owned Batches are different execution owners."}</li>
                <li>{zh ? "EMode 提供 Site diagnostic table 與完整 audit log。" : "EMode exposes the Site diagnostic table and full audit log."}</li>
              </ul>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }

  if (topic === "gateway-settings") {
    const overviewSteps: Array<[string, string]> = zh ? [
      ["Request Timeout", "單次 PPU request 等待時間"],
      ["Retry Count", "暫時性通訊錯誤的追加重試"],
    ] : [
      ["Request Timeout", "Wait time for one PPU request"],
      ["Retry Count", "Additional retries for transient communication errors"],
    ];

    return (
      <article className="documentArticle documentArticleGuide">
        <header className="documentGuideHeader">
          <p className="documentEyebrow">EMODE · SETTINGS · GATEWAY</p>
          <h1>{zh ? "Gateway 設定說明" : "Gateway Settings"}</h1>
          <p className="documentLead">{zh ? "Gateway Settings 目前只提供兩個直接可修改欄位：PPU Request Timeout 與 PPU Retry Count。不要把 system-managed backoff 或其他 runtime 行為誤認為可設定項目。" : "Gateway Settings currently exposes only two directly editable fields: PPU Request Timeout and PPU Retry Count. Do not treat system-managed backoff or other runtime behavior as configurable fields."}</p>
        </header>

        <DocumentSetupOverview
          title={zh ? "Gateway Settings　2 個可編輯欄位" : "Gateway Settings · 2 editable fields"}
          subtitle={zh ? "設定面保持小而明確；只描述 UI 現在真的可以修改的 policy。" : "Keep the settings surface small and explicit; document only policy that the current UI actually edits."}
          steps={overviewSteps}
        />

        <div className="documentGuideBody">
          <div className="documentGuideMain">
            <section className="documentProcedureSection">
              <DocumentSectionHeading number={1} title={zh ? "可編輯設定" : "Editable settings"} summary={zh ? "這兩個欄位共同形成目前 Gateway 通訊 policy。" : "These two fields form the current Gateway communication policy."} />
              <DocumentDataTable
                headers={[zh ? "欄位" : "Field", zh ? "目前定義" : "Current definition"]}
                rows={[
                  ["PPU Request Timeout", zh ? "單次 PPU request 的等待時間。預設 10 秒，可設定 1–120 秒。" : "Wait time for one PPU request. Default 10 seconds; range 1–120 seconds."],
                  ["PPU Retry Count", zh ? "暫時性 PPU 通訊錯誤的追加重試次數。預設 3，可設定 0–10；retry backoff 由系統自動管理，不可設定。" : "Additional retries for transient PPU communication errors. Default 3; range 0–10. Retry backoff is system-managed and is not configurable."],
                ]}
              />
            </section>

            <section className="documentProcedureSection">
              <DocumentSectionHeading number={2} title={zh ? "Batch policy snapshot" : "Batch policy snapshot"} summary={zh ? "已 START 的 Batch 保留當時凍結的 Gateway policy；修改只影響下一個 Batch。" : "A started Batch keeps the Gateway policy frozen at START; later edits affect only the next Batch."} />
              <DocumentCallout tone="warning" label={zh ? "修改不會回寫正在執行的 Batch" : "Edits do not rewrite a running Batch"}>
                <p>{zh ? "套用設定後應確認 revision 更新；正在執行的 Batch 仍使用 START 時的 policy snapshot。" : "After applying settings, confirm the revision advances. A running Batch continues using the policy snapshot frozen at START."}</p>
              </DocumentCallout>
            </section>
          </div>

          <DocumentTopicExampleRail topic={topic} zh={zh} />
        </div>
      </article>
    );
  }


  return (
    <article className="documentArticle documentArticleGuide">
      <header className="documentGuideHeader">
        <p className="documentEyebrow">EMODE · SETTINGS · MOCK</p>
        <h1>{zh ? "Mock 設定說明" : "Mock Settings"}</h1>
        <p className="documentLead">{zh ? "Mock Settings 用來控制 Synthetic Image、deterministic seed、operation failure injection 與 timing profile。這些設定只描述 Mock runtime，不代表真實硬體能力。" : "Mock Settings controls Synthetic Image, deterministic seed, operation failure injection, and timing profile. These settings describe Mock runtime only and do not prove real hardware capability."}</p>
      </header>

      <DocumentSetupOverview
        title={zh ? "Mock Settings　4 個設定群組" : "Mock Settings · 4 configuration groups"}
        subtitle={zh ? "先決定 Profile 與 Synthetic Image，再設定 determinism 與各 operation timing / error injection。" : "Resolve Profile and Synthetic Image first, then configure determinism and per-operation timing / error injection."}
        steps={(zh ? [
          ["Profile", "Enabled"],
          ["Synthetic Image", "Default Image Size"],
          ["Determinism", "Seed Mode / Fixed Seed"],
          ["Operation Profile", "Error Rate / Base Time / Throughput / Jitter"],
        ] : [
          ["Profile", "Enabled"],
          ["Synthetic Image", "Default Image Size"],
          ["Determinism", "Seed Mode / Fixed Seed"],
          ["Operation Profile", "Error Rate / Base Time / Throughput / Jitter"],
        ]) as Array<[string, string]>}
      />

      <DocumentCallout tone="critical" label={zh ? "Mock evidence boundary" : "Mock evidence boundary"}>
        <p>{zh ? "Mock PASS ≠ 真實 OpenOCD、Z2/FPGA、socket 或實體 IC programming 已驗證。" : "Mock PASS ≠ validation of real OpenOCD, Z2/FPGA, socket, or physical IC programming."}</p>
      </DocumentCallout>

      <div className="documentGuideBody">
        <div className="documentGuideMain">
          <section className="documentProcedureSection">
            <DocumentSectionHeading number={1} title={zh ? "Profile 與 Synthetic Image" : "Profile and Synthetic Image"} summary={zh ? "控制是否套用 Mock profile，以及未手動選 image 時的預設 synthetic image 大小。" : "Control whether the Mock profile applies and the default Synthetic Image size when no image is selected manually."} />
            <DocumentDataTable
              headers={[zh ? "欄位" : "Field", zh ? "說明" : "Description"]}
              rows={[
                ["Enabled", zh ? "開啟或關閉 Profile timing / error injection。" : "Enable or disable Profile timing and error injection."],
                ["Default Image Size", zh ? "Mock Synthetic Programming Image 的預設大小，可設定 64–4096 KiB，step 為 64 KiB。" : "Default Mock Synthetic Programming Image size, configurable from 64 to 4096 KiB in 64 KiB steps."],
              ]}
            />
          </section>

          <section className="documentProcedureSection">
            <DocumentSectionHeading number={2} title={zh ? "Deterministic seed" : "Deterministic seed"} summary={zh ? "Fixed seed 用於需要重現相同受控條件的測試。" : "Fixed seed is for reproducing the same controlled test condition."} />
            <DocumentDataTable
              headers={[zh ? "欄位" : "Field", zh ? "說明" : "Description"]}
              rows={[
                ["Seed Mode", zh ? "可選 Auto 或 Fixed；Fixed 用於需要重現相同測試條件的情境。" : "Choose Auto or Fixed. Fixed is useful when the same controlled test condition must be reproduced."],
                ["Fixed Seed", zh ? "Seed Mode = Fixed 時可設定非負整數 seed；Auto 模式時此欄位不可編輯。" : "When Seed Mode is Fixed, configure a non-negative integer seed; this field is disabled in Auto mode."],
              ]}
            />
          </section>

          <section className="documentProcedureSection">
            <DocumentSectionHeading number={3} title={zh ? "Operation failure 與 timing" : "Operation failure and timing"} summary={zh ? "E/P/V/R 可各自設定 failure rate 與模擬 timing profile。" : "E/P/V/R each have independent failure-rate and simulated timing profiles."} />
            <DocumentDataTable
              headers={[zh ? "欄位" : "Field", zh ? "說明" : "Description"]}
              rows={[
                ["E/P/V/R Error Rate", zh ? "Erase / Program / Verify / Read 各自可設定 0–100% 的 operation failure rate，解析度 0.1%；不是 Gateway/network 斷線率。" : "Each Erase / Program / Verify / Read operation has a configurable 0–100% failure rate at 0.1% resolution; this is not a Gateway or network disconnect rate."],
                ["E/P/V/R Base Time", zh ? "每個 operation 可設定基礎模擬執行時間，單位 ms。" : "Configure the base simulated execution time for each operation in milliseconds."],
                ["E/P/V/R Throughput", zh ? "每個 operation 可設定模擬 throughput，UI 單位為 KiB/s。" : "Configure simulated throughput for each operation; the UI uses KiB/s."],
                ["E/P/V/R Jitter", zh ? "每個 operation 可設定額外的 ± timing variation，單位 ms。" : "Configure additional ± timing variation for each operation in milliseconds."],
              ]}
            />
          </section>
        </div>

        <DocumentTopicExampleRail topic={topic} zh={zh} />
      </div>
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