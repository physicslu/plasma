Warning: truncated output (original token count: 16015)
Total output lines: 301

# Plasma Documentation Index

本頁是 `docs/` 的 canonical 文件入口。執行中的程式、設定 schema、REST／wire contract 與自動測試優先於描述性文字；若兩者不一致，先停止操作、以實作與測試確認事實，再在同一個變更中修正文檔。

## 文件狀態

| 標記 | 意義 |
|---|---|
| **Current** | 描述目前已實作或目前必須遵守的契約。 |
| **Reference** | 設計背景、驗證邊界或維護方式；不得取代 Current contract。 |
| **Plan** | 尚未全部實作的核准方向；不能宣稱為現有能力。 |
| **Historical** | 僅供遷移背景；不是相容性或執行契約。 |

## 跨廠牌燒錄預設安全政策

- **Current design default / 部分實作** — [Target Execution and Interrupt Isolation](architecture/programming-interrupt-isolation-policy.md)：所有 IC 的破壞性 Erase/Program 前預設須驗證目標執行隔離；具中斷的 MCU 必須採用符合 Provider 的中斷遮罩或等效策略，無 CPU／ROM ISP 則須提出適用性或例外證據。現有實機驗證僅及於 STM32F103C8T6 Z2 Site 1，其他 Provider 的 Runtime Gate 仍待實作。

## Current external SWD PoC vs retired internal fixtures

- **Current** — Z2 PS-local OpenOCD + WordPort/RemoteBitbang + paired PL SWD Image for Blue Pill: see root `AGENTS.md`, [PS OpenOCD architecture](architecture/ic-support-openocd-plan-executor.md), [retirement map](development/swd-legacy-path-retirement.md).
- **Historical / retired for real Blue Pill:** `z2-swd-gpio` PS EMIO GPIO and `z2-swd03-axi` internal synthetic DPIDR. SWD-04/05 archived fixtures are not current external target operations.

## Architecture Decision Records

- **Current** — [ADR Index](adr/README.md)：記錄 Plasma 已核准的長期架構決策與狀態。
- **Current** — [ADR-0001: PYNQ System Python 與 Plasma PPU Runtime 分離](adr/0001-pynq-system-python-plasma-runtime-separation.md)：PYNQ owns System Python；Plasma owns an isolated, Plasma-qualified Python runtime。Bundled Python 是偏好的產品方向，但必須先完成 ARMv7/PYNQ 實機 qualification。
- **Current / Accepted Policy** — [ADR-0002: IC Discovery、Catalog Level 與 Catalog 可見性統一政策](adr/0002-openocd-software-qualified-catalog-visibility.md)：所有 Manufacturer 使用 L0 `DISCOVERED` → L1 `PROGRAMMING_CANDIDATE` → L2 `PROGRAMMABLE` → L3 `PLASMA_VERIFIED`；L0 是 Internal Research Registry、一般 IC Selector 對客戶顯示 L1–L3 並提供 Level Filter、Job Picker 維持 L2/L3，L3 表示至少一組版本化 PLASMA configuration 已 HIL PASS。Active API/runtime 不保留 `phase1_*`／`phase2_*`／`phase3_*` 欄位。
- **Proposed** — [ADR-0003: Runtime FPGA Driver 與動態重新配置責任邊界](adr/0003-runtime-fpga-driver-reconfiguration-boundary.md)：UIO-first Driver 選型候選、單一 PPU FPGA Configuration Owner、Linux 無須 Reboot 的 Bitstream 切換；尚待 Z2 Kernel／UIO／Bridge 證據，不是 Accepted Contract。
- **Accepted architecture / implementation pending** — [ADR-0004: PPU Local Trust Root](adr/0004-ppu-local-trust-root-deployment-security.md)：每台 PPU 本地信任根與獨立的操作人員／Publisher 授權鏈；正式安全機制尚待 Gate 1B。

## Operator

- **Current** — [Plasma Console Operator Guide](operator/plasma-console-guide.md)：PMode／EMode、Batch Summary、操作與異常復原。

## Engineering governance and execution paths

- **Gate 1 Draft / Host-only / PR #1202** — [Root Guard 燒錄 Session 與 FPGA Configuration 准入分離](development/root-guard-runtime-program-split-2026-10-29.md)：正常燒錄取消全系統 `/proc` FD／VMA 完整掃描，保留裝置限定 `fuser`、全域 FPGA 鎖、Image／Boot／UIO Guard；FPGA Download／Test／Restore 持續嚴格掃描。尚未部署、合併或實機驗收，亦非八通道 Broker 已完成。



- **Current / Path 2 guarded-hardware operator-cli** — [PLASMA Three-Path Work Execution Model](development/plasma-three-path-execution-model.md)：現行 Path 2 通用硬體 Work Order 使用 `capability: operator-cli`、`scope: guarded-hardware`、來源 SHA 綁定的 Python `script`、`argv` 與受限 `timeout_seconds`；在非 Root SWPC Runner 執行，不自動取得 sudo／Root 權限。Exit 69／77 是失敗的 NOT_RUN，Exit 0 僅為待審證據。CPU-only／Vivado Host Build 為各自獨立能力。
- **Path 2 dynamic Vivado Host Build / PR #1210** — [PLASMA Three-Path Work Execution Model](development/plasma-three-path-execution-model.md)：工作單使用可信事件的 `main` 來源，或綁定開放 PR 精確 HEAD；專案建置契約與驗證器經真實 SWPC Path 2 建置驗收 `z2-identity`、`z2-control-waveform`。此能力只建置，不下載 FPGA 或操作 Z2；實際 `main` 狀態以 PR 是否合併為準。
- **Historical / retired z2-root-operation Work Order; F1-B #1168 evidence** — [Path 2 受保護 Z2 Root Entry 歷史契約](development/path2-generic-fpga-image-loader.md)：舊 Dispatcher 固定 `download|test|restore` Work Order 已退役，現行 Dispatcher 明確拒絕；獨立兩參數 Protected Root Entry／底層 Transport 與來源、互斥、復原守衛仍保留。#1168 實機 PASS 僅涵蓋當時 Site 1 F1-B，不能推導 Blue Pill／其他 Programmer IP／八 Site 資格。

- **Historical Gate 1 offline provider integration** — [Path 2 Real Provider Integration](architecture/plasma-path2-real-provider-integration-gate1.md)：原始 Gate 1 僅驗證 BIT/BIN、跨 Trigger Lease 與離線故障注入；Stage Transport／Protected Root Entry 為保留的底層受保護工具，不是現行 Path 2 Dispatcher 的 `z2-root-operation` Capability。實際硬體使用 `operator-cli` 時仍須逐次核對授權、映像 Hash、所有權及 Recovery 證據。

- **Historical offline coordinator contract** — [Path 2 Three-Stage Build / Download / Testing Coordinator](architecture/plasma-path2-three-stage-gate1.md)：記錄舊 Build／Download／Testing 獨立 Trigger、自動銜接與離線 Adapter／Receipt 測試；現行通用 Path 2 硬體入口為 `operator-cli`，不會自動進入舊 Coordinator／Stage Transport。底層 Protected Root 權限與復原條件仍須獨立成立。

- **Current after Gate 2 / Owner-approved Gate 1 design** — [PLASMA Three-Path Work Execution Model](development/plasma-three-path-execution-model.md)：Gate 1 由 ChatGPT 推薦並讓使用者選擇 Path 1（ChatGPT Direct Work）、Path 2（SWPC CLI Work）或 Path 3（SWPC Codex Work）；批准後在明確授權內自動執行，PR 準備妥當才請求 Gate 2 合併。包含三套流程圖、角色分工、Github Actions Dispatch 前提、證據／資安邊界與不需 PR 的純驗證任務。**這是規範，不代表通用 SWPC Dispatcher 已啟用或授權硬體操作。**

- **Current / Development Mode** — [Three Shared BLOCKING Decisions](development/development-blocking-policy.md)：Path 2／Path 3 共用授權與來源、Z2 實機安全／復原、真實回執三個核心阻擋邊界；移除重複檢查，但不繞過裝置安全條件。

## Architecture and contracts
- **Gate 1A / Host-only / Draft PR #1214** — [PPU Local Trust Root Security Contract](architecture/ppu-local-trust-root-security-contract.md)：設備身分、工廠 Provisioning、HTTPS、撤銷、重放、Factory Recovery 威脅模型與 Gate 1B WBS；不啟用正式 generic admission。
- **Gate 1A / Host-only evidence / Draft PR #1214** — [PPU Local Trust Root Gate 1A Evidence](evidence/ppu-local-trust-root-gate1a-2026-10-30/report.md)：契約測試、CI 與未完成的正式整合邊界。
- **Gate 1 / Path 1 / Draft / Host-only** — [SWPC → PPU Deployment Channel Completion](deployment/ppu-deployment-channel-completion-gate1.md)：統一 Bootstrap 上傳、通用 C／Python／FPGA Package 與既有 Deployment Engine 的整合工作規格及 Host-only 測試；實機安裝、FPGA 載入與正式授權尚未完成。
- **Gate 1 / Path 3 / Host-only evidence / Draft PR #1214** — [PPU Deployment Channel API／Coordinator 測試證據](evidence/ppu-deployment-channel-host-only-2026-10-30/report.md)：記錄 Artifact 還原、Host-only 正負向測試與未完成的實機安裝及硬體驗收。
- **Gate 1 / Path 1 / Draft / Host-only** — [PPU 單一安裝入口收斂](architecture/ppu-unified-deployment-gate1.md)：唯一 Bootstrap Deployment API、共用 Coordinator Lock/Journal 目標與 SWPC `ppu-deploy` 三模組過渡驗證；現有 SSH 工程安裝未退役、工程/FPGA Image 的新 API 仍未取得安裝資格，未部署。
- **Gate 1 / Path 1 / Host-only / Draft** — [PPU Master 非 Root 受控執行與部署契約](architecture/ppu-master-nonroot-execution-gate1.md)：重用既有 PPU Installer/Bootstrap 與 Root Guard，建立 WordPort／FPGA／Protected Root 的特權操作規劃與正負向測試；不接入真實權限、不改 Z2、不部署、不合併。
- **Gate 1 / Path 1 / Host-only / Product policy candidate** — [PPU Z2 Monitor/Master/Engineer Privilege Boundary](architecture/ppu-privilege-boundary-gate1.md)：PPU 三級產品能力、Master 非 Linux Root 操作與部署、Engineer Root 維修、特權 Bridge 的預期邊界；僅 Host-only policy／tests，尚未接入 Runtime／Z2。
- **Gate 1 / Path 1 / Source audit** — [Z2 Root Guard Rule Necessity Audit](development/z2-root-guard-rule-audit-gate1.md)：逐項核對 Root Guard、Source Pin、UIO／MMIO Owner、/proc 掃描、PPU Reload Fence、Job Lease 與 UNCERTAIN，標明必要保留、維護專用、重複候選及尚未合併的 Draft；本次不刪除受保護程式。



- **Proposed / Documentation-only / M1 NO-GO** — [PLASMA Verification Platform v1](architecture/plasma-verification-platform-v1.md)：統一 FPGA SIM-0～SIM-4 的工具與平台、PS Driver→AXI→RTL 驗證矩陣、可信任 SWPC 邊界及未來證據格式；本 PR 不變更 CI 或授權任何硬體操作。

- **Gate 1 Draft / GitHub-hosted only** — [Unified FPGA Build & Diagnostic Engine v1.0](architecture/plasma-unified-fpga-build-diagnostics-v1.md)：Path 2／Path 3 共用 Vivado Driver、階段式錯誤診斷、License／目錄前置檢查、SHA256 Artifact；本次僅驗證離線測試，未在 SWPC 重新建置，硬體 M1 NO-GO。
- **Historical Gate 1 fixed host-build capability** — [Fixed CLI Host Build Capability](architecture/plasma-path2-fixed-host-build-capability.md)：原始 Gate 1 規範 SWPC Vivado 固定 CLI 與 Capability 審核；該歷史文件的 NOT_RUN 標記不代表現有 Path 2 執行狀態。當前 Build／Download／Testing 仍依 Work Order、受信任來源及各階段安全守衛判定。
- **Gate 1 / Runtime candidate / DEFAULT OFF** — [Reusable Engineering Runtime Dispatcher v1](architecture/plasma-engineering-runtime-dispatch-v1.md)：Path 2 SWPC CLI／Path 3 SWPC Codex 共用 Work Order、Capability、SHA 與一次性保護 Claim；PR 與 push 僅執行 GitHub-hosted 離線測試。尚未啟用 SWPC 執行，隔離 Runner／自動 Gate 1 Dispatch／真實 Publisher 未驗收，不代表可操作任何實體硬體。
- **Plan / Offline-only Gate 1A** — [Unified Engineering Dispatch v1](architecture/plasma-engineering-dispatch-v1.md)：定義 versioned Work Order、SHA256 owner approval、Capability Policy、離線授權及去重契約；所有既有 Codex Workflows 不修改，僅在未來派工時逐條遷移，**尚未部署或啟用新的 Runtime Dispatcher**。
- **Plan / Offline software-pr Gate 1** — [PLASMA Software-only PR Candidate + Mock Publisher Pilot](development/plasma-engineering-software-pr-pilot.md)：Issue #981 的受控 Work Order、離線檔案變更、SHA256 證據與 Mock PR Publisher；GitHub-hosted FAKE Codex 驗證，不代表已運行真實 Codex、自動建立 PR 或啟用 Dispatcher。
- **Gate 1 / Dormant Claim Canary** — [PLASMA Engineering Protected Claim One-shot Canary](development/plasma-engineering-claim-canary.md)：Issue #981 GitHub Claim Ruleset 的實際 create/replay/update/delete/readback 驗證程式；僅 Owner 未來單次精確指令才能觸發，現在只執行離線契約測試，**未建立任何真實 Claim、未啟用 Dispatcher**。
- **Gate 1 / SWPC Codex software-only MVP / not yet live** — [Software-only Codex → PR MVP](development/plasma-codex-software-mvp.md)：Issue #981 單次 Owner 指令、真實 Codex Worker、獨立受限 Publisher 與 Gate 2 人工合併；未完成實際 Codex 執行前不得宣稱上線。
- **Gate 1 / SWPC device-node diagnostic (not executed)** — [Codex Software-only Device Permission Read-only Diagnosis](development/plasma-codex-device-permission-diagnostic.md)：針對 Run #39190291831 之硬體節點存取 NO-GO，僅提案裝置節點權限中繼資料、Linux User／Group 與 ACL 唯讀蒐集；PR 合併不會自動啟動 SWPC，實機取證另需明確批准。
- **Gate 1 / Unified AXI / M1 NO-GO** — [Fixed PPU Unified 64KiB AXI Site1](architecture/fixed-ppu-unified-axi-site1-gate1.md)：AXI AW/W 配對、Identity + Site1 同一入口、Global Fault 連動及虛擬 SWD E2E；Host-only，尚未實機驗證。
- **Gate 1 / PPU Identity / M1 NO-GO** — [PPU Global Identity & Resource Admission](architecture/fixed-ppu-global-identity-resource-admission-gate1.md)：隔離 AXI-Lite Identity、Host-only Board Descriptor／UIO Resource Discovery／Broker Site 准入與負向測試；未授權真實硬體。
- **Gate 1 / Semantic Convergence / M1 NO-GO** — [Fixed FPGA ABI v1 SWD Semantic Convergence](architecture/fixed-fpga-swd-semantics-gate1.md)：SWD 64-clock Reset、半週期、ACK／Error、FAULT ACK、Sequence／Driver 競態；Host-only，尚未實機驗證。
- **Gate 1 / Simulation-only / M1 NO-GO** — [Fixed FPGA SWD Site 1 RTL Vertical Slice](architecture/fixed-fpga-swd-site1-rtl-gate1.md)：隔離的 AXI-Lite／SWD Site 1 RTL 與模擬 Driver，Cocotb 虛擬 DPIDR 測試；不代表實體 FPGA／UIO／八通道已驗收。
- **Gate 1 / Fixed Image M1 NO-GO** — [Zynq-7020 Universal Fixed Image ABI v1](architecture/fixed-fpga-hardware-abi-v1-gate1.md)：以 SWD／SPI PIO 定義完整最小 Command／FIFO／Site 1–8／Response 契約；[機器可驗證 ABI](../pl/verification/fixed_image_abi_v1_gate1.json) 為提案，**RTL 尚未實作**。
- **Gate 1 / Host-only** — [Fixed Image UIO Driver Contract](development/fixed-fpga-uio-driver-contract-gate1.md)：依 Kernel／Device Tree／Physical Resource 唯一辨識 UIO，而非固定 uio0；不授權真實 /dev/uio*。
- **Gate 1 / Host-only** — [Single Hardware Broker + Eight-Site Ownership](architecture/fixed-fpga-hardware-broker-eight-site-gate1.md)：Execution Owner／Hardware Broker／Site Lease／獨立 DUT Power Reset 分工。
- **Gate 1 / M1 NO-GO** — [Fixed FPGA M1 Freeze Acceptance](architecture/fixed-fpga-m1-gate1-acceptance.md)：技術缺口、RTL/Driver/電氣驗證及下階段分工。
- **Plan / Proposed** — [Runtime FPGA Architecture v1.0](architecture/runtime-fpga-architecture-v1.md)：記錄一台 PPU 同批次相同 IC、多 Site 獨立執行、切換介面不重啟 Linux 的架構前提，以及 Driver／Hardware ABI／動態 FPGA Switching、HIL Phase、相依性與 Gate 邊界；**尚未實作，也不授權實機操作**。
- **Plan / Proposed** — [Runtime FPGA Hardware ABI v1](architecture/runtime-fpga-hardware-abi-v1.md)：定義 PPU 64-KiB／8-Site 候選 AXI Map、Identity／Capability、Major/Minor，相容性與現有 MS01 的語意落差；**不代表真實 RTL 已實作**。
- **Host-only review / M1 NO-GO** — [Zynq FPGA Manager Isolation and Runtime Ownership Review](architecture/zynq-fpga-manager-isolation-ownership-review.md)：以 Z2 唯讀盤點、Kernel/DT 綁定與明確標示的 Xilinx 參考原始碼，審查 UIO Ownership、PS–PL 隔離缺口及 PPU Configuration Owner；不授權 FPGA 載入或 HIL-B/C。
- **Host-only evidence review / M1 NO-GO** — [PPU Phase 2B M1 Hardware Boundary](architecture/ppu-phase2b-m1-hardware-boundary.md)：以唯讀 UIO/Manager/Bridge Inventory 的離線 Gate 拒絕未經證實的 FPGA 重配置安全主張，列出 Kernel Source、AXI Drain、DMA/VMAs 與外部復原的硬體阻擋證據；不授權實機操作。
- **Current** — [Facility / PPU / Site Domain Model](architecture/ppu-facility-sites.md)
- **Current** — [PPU Execution Ownership](architecture/ppu-execution-ownership.md)
- **Current** — [Domain Naming and Identity Policy](architecture/domain-naming-migration.md)
- **Current** — [Web Product Modes](architecture/web-product-modes.md)
- **Current** — [Web REST API Contract](architecture/web-rest-api-contract.md)
- **Current** — [Configuration Architecture](architecture/configuration-architecture.md)
- **Current** — [PPU Site Configuration](architecture/ppu-site-configuration.md)：定義 Phase 1 `enabled`／`interface`／`target` desired state、PPU authoritative validation、canonical YAML atomic persistence、active-execution write gate、desired／actual reconciliation 與 Manager/BFF allowlist 邊界。
- **Current** — [CI/CD Validation Architecture](architecture/ci-cd-validation-architecture.md)：定義 risk-based validation topology、Fast／Browser／Runtime／Release gate、Device Catalog Historical／Current 邊界，以及 production Device Catalog → IC Support 的跨 domain dependency。
- **Gate 1 / Draft / Archive not yet approved** — [ICPN Catalog Workflow Rationalization — 2026-10-19](engineering/ci/icpn-workflow-rationalization-2026-10-19.md)：262 筆 Workflow 快照與首批兩個 Microchip 歷史 One-shot 歸檔候選；未完成全部 Actions Run History／Classic Branch Protection 驗證，沒有 Gate 2 合併授權。
- **Reference** — [Device Catalog CI Coverage Map](architecture/device-catalog-ci-coverage-map.md)：記錄 Device Catalog workflow authority、trigger、validator、overlap 與 lifecycle；coverage parity 證明前不授權 workflow retirement。
- **Gate 1 / Draft / GitHub-hosted Shadow only** — [STM32 Historical Governance Shadow Dispatcher](engineering/ci/stm32-governance-shadow-gate1.md)：以原三份 Workflow 的固定 Git Blob、Trigger 聯集、Validator 命令、Runner、Timeout 與負向測試驗證同等性；原 Workflow 不變、不退役，不授權合併或實體硬體操作。
- **Current** — [Batch Domain Model](architecture/batch-domain-model.md)
- **Current** — [Server-side Batch Runtime](architecture/server-side-batch-runtime.md)
- **Current** — [Batch Persistence and Gateway Restart Recovery](architecture/batch-persistence-recovery.md)
- **Current** — [Plasma Gateway Communication and Recovery](architecture/gateway-communication-recovery.md)
- **Current** — [PPU Network Configuration](architecture/ppu-network-configuration.md)：定義 Phase 1 `eth0` desired-state API、Default Gateway／DNS 等 Linux network 參數、驗證、持久化與 Phase 2 activation／reconnect／rollback 邊界；並區分 Plasma Gateway service 與 Linux Default Gateway。
- **Reference** — [Virtual PPU Network Lab](architecture/virtual-ppu-network-lab.md)：以 Linux host 上的 production Plasma Manager 驅動兩個 isolated packaged ARMv7 Virtual PPU，驗證 real managed-IPv4 migration、same-`ppu_id` reconnect、activation commit、Manager registry CAS／journal 與 privilege separation；不代表 PYNQ-Z2 native network backend acceptance。
- **Reference** — [Static IPv4 Fault Injection](architecture/static-ipv4-fault-injection.md)：在 fresh isolated Virtual PPU topology 注入 duplicate candidate、wrong `ppu_id`、reconnect timeout、helper failure 與 Manager pre/post-commit crash，驗證 rollback、`recovery_required`、registry fail-closed 與 restart reconciliation；不代表 PYNQ-Z2 native network backend acceptance。
- **Current** — [Persistent Integration Host Qualification](architecture/persistent-integration-host-qualification.md)：定義 L4 main-only post-merge qualification、self-hosted/rootful-Docker threat model、fail-closed preflight、runner enrollment boundary，以及為何目前不能把長期 runner 當成 arbitrary-PR execution worker。
- **Current** — [Production Real-Path Loopback Diagnostics](architecture/diagnostics-real-path-loopback.md)
- **Current** — [Control Plane Routing Architecture](architecture/control-plane-routing-architecture.md)：定義 Control Console、BFF、Plasma Manager、Plasma Gateway、Plasma Server 的責任邊界，以及 Managed Mode 的 Programming／Loopback 共用 production route。
- **Current** — [Manager Runtime PPU Registry](architecture/manager-runtime-ppu-registry.md)：定義 Manager-owned runtime inventory、Plasma Gateway Endpoint、`pending`／`commissioned`／`disabled` lifecycle、Add／Validate & Enable／Disable／Remove 與 durable state 邊界。
- **Reference** — [Remote Write Security Boundary](architecture/remote-write-security-boundary.md)
- **Current** — [PMode Factory Console v2](architecture/pmode-factory-console-v2.md)
- **Current** — [Engineering Programming Workspace](architecture/engineering-programming-workspace.md)
- **Current** — [Engineering Programming Observability](architecture/engineering-programming-observability.md)
- **Current** — [Engineering Settings UI Design System](architecture/engineering-settings-ui-design-system.md)
- **Plan / Accepted Policy** — [IC Information Catalog Level 0 Evidence Contract](architecture/ic-information-phase1.md)：歷史檔名保留 `phase1`，但正式語意為 Level 0 Exact ICPN identity/evidence；具 programming route 才升 L1，qualification `SUPPORTED` 才升 L2，HIL PASS 才升 L3；L0 僅供 Internal Research，Customer IC Selector 從 L1 開始。
- **Current** — [IC Selector Architecture](architecture/ic-selector.md)
- **Current** — [IC Selector Upstream Evidence / Binding Contract Gate A](architecture/ic-selector-upstream-evidence-consistency-gate-a.md)：區分 OpenOCD 上游 CFG／Driver／DEVID、Production CFG Binding 與 Programming Qualification。
- **Implementation / Proposal** — [Installed OpenOCD Evidence Root v1](architecture/runtime-evidence-root-implementation-v1.md)：修正 source-only H5/C5/OpenOCD Provider 顯示資訊在非 editable Python 安裝下的路徑解析，區分 Render full 與 Slim PPU 必備／可省略來源；不授權燒錄。
- **Implementation / Proposal** — [KL25 Installed Backend Lock Root v1](architecture/kl25-runtime-backend-lock-root-v1.md)：以既有 IC Support Root 契約載入固定的 KL25 implementation lock，non-editable 安裝與 fail-closed 測試通過才能合併；不新增 KL25 Operation Admission。
- **CI / Architecture Contract** — [Runtime Data Root Contract v1](architecture/runtime-data-root-contract-v1.md)：所有可安裝 Python 模組使用明確 Data Root，AST CI 禁止新增 wheel `__file__` 相對路徑推算；只保留 2 個受控 Source-tree 開發例外，並守護 NXP、OpenOCD 與 KL25 Root Resolver。
- **Current** — [Selected IC Profile v1](architecture/selected-ic-profile-v1.md)：將 exact ICPN 的 Device operating characteristics、Programming requirements、Backend evidence 與 PLASMA compatibility 分層組合；STM32F103C8T6 為第一個 manufacturer-first pilot。
- **Current / Design-input contract** — [Programming Hardware and Socket Profile v1](architecture/programming-hardware-socket-profile-v1.md)：以 STM32F103C8T6/LQFP48/SWD 建立 physical pin map、全部供電/接地 contact、NRST/BOOT0 與 package geometry 的 machine-readable Socket design input；明確不宣稱 socket vendor、signal integrity、runtime hardware、HIL 或 execution readiness。
- **Gate 1 / Source-only L2 提案（Draft、未合併）** — [STM32F103 Medium-density 非 LQFP 12 顆 exact-ICPN 資格擴展](architecture/stm32f103-medium-nonlqfp-l2-v9.md)：8 顆直接適用性、4 顆 T…4015 tokens truncated…
- **Gate 1 retirement / Host-only** — [Z2 SWD-05 Legacy Dedicated Dispatch Retirement](development/plasma-z2-swd05-legacy-retirement-gate1.md)：退役 Issue #981 既有專用派工 Workflow／SWPC CLI／歷史 Route；保留 SWD-05 Linux Driver、原本受保護的 FPGA Owner Lock 與 Path 2／3 執行介面，不代表 SWPC 或 Z2 已執行清理。
- **Historical / Issue #981 legacy triggers retired** — [舊 Codex 觸發器退役紀錄](development/plasma-legacy-codex-issue981-trigger-retirement.md)：歷史 9 個 Issue 入口已停用；其中 LA2016 三條 Supervisor／Direct A/B／診斷 Workflow 連同過時腳本在 2026-10-26 移除。現行硬體工作統一使用通用 Path 3，不再恢復舊指令。
- **Host-only reference review / M1 NO-GO** — [PPU Phase 2C: Z2 Kernel Source Lineage and AXI Isolation](architecture/ppu-phase2c-z2-kernel-source-lineage-axi-review.md)：釘選 Xilinx 2024.1 參考驅動 Git Blobs，分離 Z2 目標 Kernel/DTB 未匹配來源事實，審查 Manager 與 Region 的不同隔離路徑；不授權實機載入。
- **Gate 1 / read-only inventory** — [Z2 Kernel/Device Tree Read-only Inventory](development/z2-kernel-dt-readonly-gate1.md)：限定唯讀 Kernel Config、Device Tree、FPGA Manager／Region／Bridge 與 UIO metadata；Host 假資料驗證與獨立 SWPC Codex 實機取證分開，M1 維持 NO-GO。
- **Current** — [Codex Cloud Environment](development/codex-cloud-environment.md)
- **Current** — [Local AI Development Guide](development/local-ai-development-guide.md)
- **Current** — [Persistent Integration Runner Enrollment](development/persistent-integration-runner-enrollment.md)：定義 L4 host readiness、GitHub runner enrollment/restriction、首次 qualification、staleness、upgrade、revoke 與 recovery lifecycle；不把 registration token 或 host provisioning 寫入 repository automation。
- **Reference** — [IC Support Local-AI Benchmark Handover](development/ic-support-ai-benchmark-handover.md)：整理 STM32F103C Qwen 實驗的能力邊界、已知 failure classes、multi-model role separation，以及下一輪獨立 Gemma 比較的 blind-control 條件。
- **Current** — [IC Support Semantic Validator v0](development/ic-support-semantic-validator-v0.md)：把 Qwen／Gemma 已觀察到的機械性 failure class 轉成 deterministic semantic invariants、negative regressions 與 CI gate；未具 execution IR 的規則明確維持未實作狀態。
- **Reference** — [STM32F103 Manufacturer-Derived Programmer Codegen Pilot](development/stm32f103-programmer-codegen-pilot.md)：從 manufacturer-derived baseline／Programming Profile／Execution IR 產生 software-only reference programmer，再與 pinned OpenOCD semantic review 做 post-generation differential；不代表 HIL 或實體燒錄 readiness。
- **Reference** — [STM32F103 Real OpenOCD Binary Software Acceptance](development/stm32f103-openocd-real-binary-acceptance.md)：以真正 source-pinned OpenOCD binary、official dummy adapter 與 `target/stm32f1x.cfg` 驗證 C8 64-KiB Flash-driver registration；`noinit` 保證不進入 adapter／target hardware initialization。
- **Current** — [Multi-machine Development Guide](development/multi-machine-development-guide.md)
- **Current** — [VS Code Remote Workspace Standard](development/vscode-remote-workspace.md)
- **Current** — [Integration Host Deployment Guide](development/swpc-deployment.md)
- **Reference** — [Microchip Phase 1 SWPC Evidence Vault Handoff](development/microchip-phase1-swpc-evidence-vault-deployment-v1.md)：原廠 Artifact SHA-256 鎖定、SWPC 現場 Preflight、手動 Vault 存入與還原驗收；不宣稱已實際部署或完成異地保存。
- **Current** — [Secure Gateway Deployment](development/secure-gateway-deployment.md)
- **Current** — [Fleet Demo Deployment](development/fleet-demo.md)
- **Current** — [Mock Continuous Delivery](development/mock-cd.md)
- **Current** — [Mock Runtime Operator Guide](development/mock-runtime-operator-guide.md)
- **Current** — [Operator Acceptance Test Matrix](development/operator-acceptance-test-matrix.md)
- **Current** — [Programming Image Observability Test Plan](development/programming-image-observability-test-plan.md)
- **Current** — [Runtime Acceptance](testing/runtime-acceptance.md)
- **Current / Prototype Execution Contract** — [PYNQ-Z2 Codex Autonomous HIL Command](development/codex-z2-hil-development-command.md)：可重複使用的 Codex 任務指令、私有 SSH／sudo 認證介面與 PSPL-02／SWD-00 實機測試／復原驗收標準；文件不代表實機測試已完成。
- **Current** — [FPGA Development Guide](development/fpga-development-guide.md)
- **Gate 1 / Host-only candidate** — [F1-B Licensed SWPC Runner Build](development/f1b-licensed-host-build.md)：Path 3 Sandbox 授權失敗的證據、受信任 Runner 修復候選與真實 Build 驗收路徑；候選尚未啟用，Build 未因此宣告 PASS。
- **Current** — [FPGA Verification Guide](development/fpga-verification-guide.md)
- **Gate 1 / Host-only / M1 NO-GO** — [V2 PS Driver → AXI BFM → Fixed ABI Site-1 RTL Verification](development/fixed-abi-v2-ps-pl-host-verification-gate1.md)：固定 ABI v1 單 Site RTL 的真實 AXI 模擬失敗案例、可重現工具版本與未涵蓋的實體 PS／PL 邊界。
- **Current** — [PLASMA FPGA SystemVerilog Coding Standard](development/fpga-systemverilog-style.md)：規範新 RTL 的可移植語法、FSM／Type／Width、AXI/Response 與 SWD／Programming Site 驗證標準。
- **Reference / Operator-observed / HARDWARE NO-GO** — [2026-10-15 PYNQ-Z2 HIL Hardware Inventory](development/hil-hardware-inventory.md)：記錄 Transcend Hub Port 2／3／4、Z2 JTAG／UART 與 5V 供電主張、AX88179、KINGST LA2016、PL 執行環境及復原驗收缺口；不含操作端識別資料，也不取代即時安全預檢。
- **Observed / LA-only functional PASS** — [2026-10-16 KINGST PWM1 → CH0 Loopback Evidence](evidence/la2016-pwm-loopback/2026-10-16/README.md)：保存 1 kHz／50% 與 2 kHz／25% 實測波形、OFF 對照、SHA256 與離線重算工具；不代表 Z2 或類比電壓驗收。
- **Observed / ST-LINK SWD reference** — [2026-10-23 STM32F103 Blue Pill Golden Reference](evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md)：保存三輪 ST-LINK Flash／讀回、六份 LA2016 原始 SWD 波形與離線驗證；CDC 首次 ID 與 SWCLK 時序差異仍未結案，不代表 Z2 燒錄能力。
- **Observed / Z2 DPIDR FAIL** — [2026-10-26 Z2 PS OpenOCD + LA2016 Blue Pill Evidence](evidence/bluepill-z2-dpidr-la2016-2026-10-26/README.md)：保存已載入 FPGA 映像的 Identity PASS、兩份原始 LA2016 波形、PS-local Bridge／OpenOCD 失敗收據與測後狀態；第二次擷取的 CH0／SWCLK 全程無邊緣，根因未定。
- **Observed / Z2 SWD + page-18 Flash + CDC PASS** — [2026-10-27 實驗步驟與證據](evidence/bluepill-z2-flash-2026-10-27/README.md)、[繁體中文摘要](evidence/bluepill-z2-flash-2026-10-27/SUMMARY.md)、[Step 1–2 原始紀錄](evidence/bluepill-z2-flash-2026-10-27/receipts/step12-result.md)：保存 FPGA BIN/Manifest、PS-local OpenOCD 程式、LA2016 波形、約 3.6 kHz SWCLK 實測、page-18 同內容擦寫讀回及 SWD reset 後 USB CDC heartbeat；未知內容的最後一頁沒有擦除或公開。
- **Observed / Z2 Blue Pill v0.1 erase/write FAIL → no-erase write PASS** — [2026-10-28 v0.1/v0.2 實驗紀錄](evidence/bluepill-z2-ab-flash-failure-2026-10-28/README.md)：首次 v0.1 擦除後寫入演算法逾時，全片讀回確認前 19 頁全 `0xFF`；之後不擦除直接寫回 v0.1，獨立讀回、同步 LA2016 活動及 reset 後 CDC heartbeat PASS。v0.2 未執行；私有 Flash/波形未公開。
- **Reference / Operator-observed Tool Runbook** — [ST-LINK SWD 工具操作手冊](development/stlink-swd-tool-operations.md)：整理已驗證的 st-info/st-flash 操作、ST-LINK 排他接線、VTref、Flash Write + 獨立 Readback／SHA256，以及 Reset/NRST 未驗證限制；文件本身不授權實機操作。
- **Current / Path 3 direct tools** — [Path 3 Codex 直接操作 LA2016／Z2 PS](development/plasma-path3-direct-hardware-tools.md)：不透過固定 JSON Host Supervisor，沿用 sigrok CLI、既有 SSH、Z2 PS OpenOCD／WordPort，保留實體互斥、電氣、Manifest 與 Root Guard。原 Issue #981 LA-only workflow 已退役；本次無實機執行。
- **Reference / Operator-observed Tool Runbook** — [KINGST LA2016 工具操作手冊](development/la2016-tool-operations.md)：實測 sigrok AppImage 與 firmware resource 初始化、被動 SWD 抓波形、成功 Golden Reference、PWM1→CH0 Loopback、PWM OFF 波形驗證；區分歷史成功與當次裝置狀態。
- **Host-only / HARDWARE NO-GO** — [PSPL-02 / SWD-00 Internal Waveform HIL](development/pspl02-swd00-hil-runbook.md)：三區段 baseline 專用的產物校驗、預檢、受限 MMIO 與原映像復原程序；現場獨立復原及 privileged ownership 尚待確認。
- **Plan / Accepted Policy** — [SWD-04 Z2 PS/PL HIL Runbook](development/swd04-z2-hil-runbook.md)：以獨立 Preflight、白名單 AXI MMIO、DPIDR、ABORT 與恢復原 PYNQ 系統的 Host-only 安全契約，實機驗證尚未執行。
- **Host-only / Execution Preparation** — [SWD-04 Offline Execution Checklist](development/swd04-offline-execution-checklist.md)：真實 Artifact、BIN 格式、離線工具包、服務隔離與 HIL／Recovery 操作單；缺少復原檔案時禁止載入。
- **Host-only software integration** — [SWD-05 Linux PS SWD Transaction Driver](development/swd05-linux-swd-transaction-driver.md)：基於 SWD-03 AXI ABI 的單 Site Driver、注入式 MMIO、Response ACK、WAIT/FAULT/ABORT、posted AP read 與故障隔離；目前無 Z2 實機資格。
- **HIL-A1.5 / GitHub-hosted QEMU / SWPC NOT RUN / M1 NO-GO** — [ARMv7 Barrier Frozen Artifact QEMU Validation](development/hil-a15-qemu-armv7.md)：以固定 GitHub A1 Run/Artifact、SHA256、ARMv7 QEMU `ctypes` 1,000 次呼叫做 CPU-only 模擬驗證；SWPC 常駐 QEMU 僅建立受控執行方案，實體 Z2 A2 仍 NOT RUN。
- **HIL-A2 / Path 2 Gate 1 preparation / Z2 NOT RUN / M1 NO-GO** — [Cortex-A9 CPU-only Native DMB Contract](development/hil-a2-cpu-only.md)：沿用共用 Dispatcher 與固定 A1 Artifact，定義預設關閉的實機 CPU-only Capability、Work Order、離線驗證及獨立 Evidence；不授權 SWPC／Z2 實機執行。
- **HIL-A1 / GitHub-hosted cross-build / M1 NO-GO** — [ARMv7 Barrier SWPC A1 / Z2 A2](development/armv7-barrier-hil-a.md)：A1 於 GitHub-hosted 以固定 Debian OCI／APT Snapshot 交叉編譯 ARMv7 ELF、驗證 `dmb sy` 並上傳 SHA256 Artifact；原 SWPC A1 實測因工具鏈缺失 FAIL；A2 Z2 執行仍為 NOT RUN。
- **P0 / Host-only / M1 NO-GO** — [Fixed ABI Site 1 Native-Word MMIO Adapter + ARMv7 DMB Candidate](development/p0-fixed-abi-site1-mmio-adapter-host.md)：沿用 LinuxMMIO 的 Site lease、嚴格 ABI 讀寫白名單、要求 Write Barrier 並驗證 COMMIT 順序；原生 ARMv7 Library、實體 Z2／DUT 尚未合格。
- **Gate 1 / Paths 1+3 / Draft** — [Native C WordPort Bridge](development/native-c-wordport-gate1-host.md)：在既有 Z2 PS 受保護 Python Owner／Site lease 與本機 UNIX Socket 內，以 SHA-pinned ARMv7 C 處理 Remote Bitbang GPIO/MMIO/DMB；原始 Protocol A/B 為 Host-only 測試，後續經核准實測 DPIDR、v0.1 Flash 與 heartbeat。總 session alarm 600 秒、socket idle 60 秒；[公開執行腳本與操作索引](evidence/native-c-wordport-2026-10-28/README.md)保存可審查來源，原始波形及 Flash 讀回保留於私有工作目錄。
- **Gate 1 / Host-only candidate / Path 2** — [Image-agnostic Native C WordPort Programming](development/image-agnostic-wordport-path2.md)：每次 Work Order 動態選擇原始 BIN 與獨立 SHA256，依 exact ICPN Programming Profile／Flash Geometry 計算 Erase；OpenOCD Verify 必要、完整 Readback 選用，使用既有 Z2 PS OpenOCD／PL WordPort；目前只准 STM32F103C8T6 Site 1，尚未部署及執行新的實機驗證。
- **Gate 1 / Draft PR #1207 / Host-only** — [通用 PPU 工程模組部署 `ppu-deploy`](development/ppu-deploy-engineering-modules.md)：Z2 PS WordPort／OpenOCD Python 整合與 SWPC A/B Runner 由同一來源版本協調部署，包含 SHA、互斥、啟用驗證與回滾；目前只有 Host-only 測試，不代表 GitHub PR 已合併或 Z2／SWPC 已部署。
- **Gate 1 / Path 2 guarded-hardware / Draft** — [Native C WordPort v0.2 SWPC→Z2／Z2 Direct](development/native-wordport-v02-path2.md)：重用 PR #1199 PS-local Native C Bridge，新增固定入口與來源 SHA、v0.2 62,800-byte 一次性 Erase／Program／Verify／Readback，失敗時於同一 OpenOCD 工作階段先讀 DHCSR／FIFO／FLASH 狀態再 Halt 讀 PC／xPSR。GitHub-hosted 僅 Host-only 測試；SWPC／Z2／DUT 執行仍 NOT_RUN，禁止自動重試、Reset 或部署。
- **Gate 1 / Draft / PR #1203** — [SWD Performance Baseline 與階段量測](development/swd-performance-baseline-2026-10-29.md)：紀錄既有 A/B 原始證據、monotonic 階段時間與 Native C／WordPort 計數器對帳；實機新 A/B 量測須符合 Owner/SHA 與 Site 1 安全授權。
- **Gate 1A / GitHub-hosted SIM-1／SIM-2** — [Fixed ABI v1 Dual-Site RTL + Protocol-neutral PS↔PL Driver](development/fixed-abi-dual-site-gate1a.md)：Site1／Site2 真實 RTL 模擬引擎、正式 PS SWD Controller 閉環及負向隔離；不代表 Z2／DUT／八 Site 實體驗證。
- **Host-only software integration** — [Linux MMIO Backend v1](development/linux-mmio-backend-v1.md)：正式 Python 模組使用 native 32-bit mmap 存取、Register Allowlist、Site Lease、Thread Safety 與生命週期保護；已完成 SWD-03 Development HIL（2026-10-16），但未涵蓋 LT02 新 IP。
- **Host-only candidate / NO REAL UIO HIL** — [UIO Runtime Backend Phase 2A](development/uio-runtime-backend-host-v1.md)：實作 Fake sysfs／Regular File 專用 UIO mapN、精確物理資源 Pin、Site Lease、Mapping Generation、Failure Injection；**拒絕開啟 `/dev/uioX` Character Device**，M1 仍 NO-GO。
- **Host-only model / M1 NO-GO** — [PPU Configuration Owner Phase 2A.1](development/ppu-configuration-owner-phase2a1-host.md)：單一 PPU Admission Gate、同 IC 批次、Quiesce、Synthetic Ownership/Safe-IO 模擬、Lease／Mapping Generation、Fault Injection；**不具實體 FPGA/Kernel 隔離資格**。
- **Host-only interlock / M1 NO-GO** — [PPU Configuration Owner Phase 2A.3](development/ppu-configuration-owner-phase2a3-interlock-host.md)：以相同 Boot／Source／Resource／Owner Epoch／Mapping Generation 將 Phase 2A.2 Safety Contract 接入 Ownership、Isolation、Retirement、Verification 與 Mapping Generation 狀態門禁；合成 PASS **不**授權真實 FPGA 載入。
- **Host-only model / M1 NO-GO** — [PPU Configuration Safety Contract Phase 2A.2](architecture/ppu-phase2a2-configuration-safety-contract.md)：驗證合成 Ownership／AXI Isolation／Mapping Retirement／Verification 證據之精確 Pin 與 fail-closed 條件；通過不授予 FPGA 載入或實體操作權限。
- **Implementation candidate / NO Z2 HIL** — [LT02 PS–PL MMIO Loopback ABI](development/mmio-lt02-ps-pl-loopback.md)：新增 FPGA AXI4-Lite Scratchpad／LinuxMMIO 分塊資料比對契約；五 Aperture Build 已由 SWPC 回報 PASS，LT02-05 Z2 HIL 尚未執行，PL UI Endpoint 仍停用。
- **HIL preparation / NOT RUN** — [LT02-05 Z2 native LinuxMMIO development HIL runner](../pl/hil/lt02/README.md)：使用正式 Python Driver + ARMv7 native LinuxMMIO；當次 image 身分、五 Aperture 檢查與原始 FPGA 恢復各自驗證，不等於 HIL PASS。
- **Host-only differential** — [SWD-06 RTL ↔ Python Differential Verification](development/swd06-rtl-python-differential.md)：由 SWD-05 Python Driver 操作 SWD-03 真實 RTL 的 Cocotb AXI4-Lite Bus，僅驗證模擬硬體，Z2 實機尚未執行。
- **Reference** — [Mock Runtime Foundation Notes](development/mock-runtime-foundation-notes.md)
- **Plan** — [Device Support Catalog Implementation Plan](development/device-support-implementation-plan.md)
- **Plan** — [OpenOCD Part-number Expansion Plan](development/openocd-part-number-expansion-plan.md)
- **Plan** — [Development Debt Register](development/todo.md)

## Deployment

- **Current** — [Deployment Index](deployment/README.md)
- **Current** — [`plasmactl` Deployment Profiles](deployment/plasmactl-deployment-profiles.md)：定義統一 operator CLI、`integration`／`local-control-station`／`swpc-z2like` profile ownership、activation rollback 與 qualification boundary。
- **Current** — [Deployment Port / Profile Matrix](deployment/port-profile-matrix.md)：定義 production、SWPC engineering 與 `z2like-demo` scenario 的 profile-specific port ownership、exposure 與安全邊界。
- **Current** — [Local Control Station Reference Deployment](deployment/local-control-station.md)：定義 Linux user-systemd 的 Console/BFF + Manager 本機參考部署、可設定 PPU Endpoint、loopback-only ingress、immutable release 與 rollback；macOS／Windows 保留相同產品契約但使用平台原生 packaging。
- **Current** — [Product Deployment Foundation](deployment/product-deployment-foundation.md)：定義跨平台 Control Station（macOS／Linux／Windows）、Z2 PPU、SWPC integration host 的產品部署責任邊界，以及 immutable release 與跨平台 read-only readiness audit。
- **Current** — [Product Release Format v1](deployment/product-release-format.md)：定義 product version、release manifest、角色／平台 artifact matrix、SHA-256 integrity、safe verification 與 clean-extraction acceptance。
- **Current** — [Control Station Runtime Packaging](deployment/control-station-runtime-packaging.md)：定義 source-tree-independent Vinext standalone Console/BFF、Manager Python zipapp、runtime manifest 與 Control Station release payload。
- **Current** — [PPU Runtime Packaging](deployment/ppu-runtime-packaging.md)：定義 Z2 PS Phase-1 source-tree-independent PPU Python zipapp、`linux-armv7l` immutable release、PS-only fail-closed configuration、systemd topology與 Managed PS Loopback 驗收邊界。
- **Current** — [PYNQ-Z2 PS Installer and Managed Loopback Acceptance](deployment/z2-ps-installer.md)：定義 verified PPU release → immutable side-by-side install、PYNQ/System-Python ownership isolation、explicit Plasma Python >= 3.11 binding、systemd activation/rollback、local readiness 與 real Managed PS Loopback evidence boundary。
- **Reference** — [PPU Bootstrap Factory Provisioning and Z2 HIL](deployment/ppu-bootstrap-factory-and-hil.md)：定義獨立 Bootstrap／recovery service、Console-managed Z2 Runtime deployment、durable rollback/recovery contract，以及 real PYNQ-Z2 HIL qualification 邊界。
- **Current** — [SWPC z2like-demo QEMU ARMv7 Backend](deployment/z2like-demo-qemu.md)：固定 SWPC 為唯一 simulation environment、QEMU ARMv7 simulated Z2 為 `z2like-demo` 唯一 PPU backend，並定義 Bootstrap/Control Station 私有路由與非實機 qualification 邊界。
- **Reference** — [Render Control Station -> SWPC Z2-like PPU Managed PS Loopback](deployment/render-swpc-managed-ps-loopback.md)：定義 Render-hosted Control Station／Manager → restricted HTTPS ingress → SWPC PS-only PPU surrogate 的 public managed qualification，以及 x86_64／ARMv7、PYNQ、PL／hardware 非等價證據邊界。
- **Current** — [SWPC Z2-like Secure Managed Programming Ingress](deployment/swpc-z2like-managed-programming-ingress.md)：在保留 diagnostics ingress 與 loopback-only full Gateway 的前提下，新增 Cloudflare Access service-token 保護、route/method allowlist 的 managed mock Programming ingress；不構成 Z2／PL／real-IC qualification。
- **Current** — [SWPC Z2-like Configured Mock Programming](deployment/swpc-z2like-configured-mock-programming.md)：將 Engineering Programming 綁定到 canonical `lab/swpc-z2like-01/SITE1..SITE8` 與既有 Plasma Server，明確拒絕 non-mock Site，且不建立舊 32-PPU demo topology；僅屬 software/mock qualification。
- **Reference** — [PPU ARMv7 Runtime Lab](deployment/ppu-armv7-runtime-lab.md)：定義 integration-host QEMU ARMv7 一鍵 runtime/resource 診斷、live／ready／PS Loopback 路徑隔離與非 Z2-HIL 證據邊界。
- **Development HIL / PASS** — [2026-10-16 Z2 Native MMIO](evidence/mmio-development/2026-10-16.md)：實機 HIL01 Identity／Build ID、HIL02 CONTROL echo 與內部 DPIDR `0x2BA01477`，原始映像及驅動已還原；不包含外部 DUT 或完整 qualification。
- **Hardware Acceptance / FULL PASS** — [2026-10-14 PYNQ-Z2 Identity-only PS/PL HIL](evidence/hil-pspl-01/2026-10-14-pynq-z2/README.md)：HIL-PSPL-01 八個 AXI GP0 Identity 讀值及原平台復原；不包含 AXI write、直接 RRESP、FPGA SWD Master 或 IC programming。
- **Offline Preparation / HARDWARE NO-GO** — [2026-10-15 PSPL-02 / SWD-00](evidence/hil-pspl-02/2026-10-15-offline/README.md)：離線測試、既有 Vivado 證據與候選／復原產物校驗；新 Z2 HIL 均為 NOT RUN。
- **Reference** — [2026-09-02 SWPC/QEMU ARMv7 Runtime Evidence](evidence/armv7-runtime/2026-09-02-swpc-qemu/README.md)：歸檔實測 JSON 與工程判讀；僅屬 SWPC/QEMU ARMv7 userspace evidence，不代表 PYNQ-Z2 native memory acceptance。
- **Reference** — [Control Station Runtime Acceptance Evidence](deployment/control-station-runtime-acceptance.md)：定義 macOS／Linux／Windows clean-runtime CI 的證據範圍與不可延伸宣稱的邊界。
- **Current** — [macOS Control Station Installer Pilot](deployment/macos-control-station-installer-pilot.md)：定義 unsigned `.pkg`、per-user `launchd` LaunchAgents、absolute Node/Python runtime binding，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing/notarization readiness。
- **Current** — [Windows Control Station Installer Pilot](deployment/windows-control-station-installer-pilot.md)：定義 unsigned MSI、WinSW-backed Windows SCM services、`Program Files`／`ProgramData` 邊界，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing 或真正 Windows operator-host readiness。
- **Historical** — [SWPC Public Preview / Mock Environment](deployment/swpc-public-preview.md)：記錄 `plasma.open4th.com` 過去作為 SWPC Preview／Mock ingress 的退役角色；目前 Mock Demo 已移至 `plasma-demo.open4th.com`，SWPC hostname 保留給 Local Control Station 驗收後切換。
- **Current** — [Web Runtime Hygiene](deployment/web-runtime-hygiene.md)
- **Current** — [Manager BFF Runtime Wiring](deployment/manager-bff-runtime-wiring.md)
- **Current** — [Render Free Public Mock Demo](deployment/render-free-public-demo.md)
- **Current** — [Render Public Smoke Acceptance](deployment/render-public-smoke.md)
- **Current** — [Render Public Browser Acceptance](deployment/render-public-browser.md)

## Component contracts outside `docs/`

- [Python control plane](../software/python/README.md)
- [Protocol v3.3](../software/python/docs/protocol.md)
- [Python architecture](../software/python/docs/architecture.md)
- [Error model](../software/python/docs/errors.md)
- [Python test guide](../software/python/docs/test-guide.md)
- [Web Console](../software/web/README.md)
- [FPGA / PL](../pl/README.md)

## Validation

Run the documentation integrity guard before review:

```bash
python scripts/tests/test-documentation-integrity.py
```

The guard checks Markdown headings and local links, verifies that every `docs/**/*.md` file is listed here, rejects known retired document names and protocol/config drift, and protects the canonical Gateway base-module name.
