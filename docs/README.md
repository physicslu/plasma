# Plasma Documentation Index

本頁是 `docs/` 的 canonical 文件入口。執行中的程式、設定 schema、REST／wire contract 與自動測試優先於描述性文字；若兩者不一致，先停止操作、以實作與測試確認事實，再在同一個變更中修正文檔。

## 文件狀態

| 標記 | 意義 |
|---|---|
| **Current** | 描述目前已實作或目前必須遵守的契約。 |
| **Reference** | 設計背景、驗證邊界或維護方式；不得取代 Current contract。 |
| **Plan** | 尚未全部實作的核准方向；不能宣稱為現有能力。 |
| **Historical** | 僅供遷移背景；不是相容性或執行契約。 |

## Current external SWD PoC vs retired internal fixtures

- **Current** — Z2 PS-local OpenOCD + WordPort/RemoteBitbang + paired PL SWD Image for Blue Pill: see root `AGENTS.md`, [PS OpenOCD architecture](architecture/ic-support-openocd-plan-executor.md), [retirement map](development/swd-legacy-path-retirement.md).
- **Historical / retired for real Blue Pill:** `z2-swd-gpio` PS EMIO GPIO and `z2-swd03-axi` internal synthetic DPIDR. SWD-04/05 archived fixtures are not current external target operations.

## Architecture Decision Records

- **Current** — [ADR Index](adr/README.md)：記錄 Plasma 已核准的長期架構決策與狀態。
- **Current** — [ADR-0001: PYNQ System Python 與 Plasma PPU Runtime 分離](adr/0001-pynq-system-python-plasma-runtime-separation.md)：PYNQ owns System Python；Plasma owns an isolated, Plasma-qualified Python runtime。Bundled Python 是偏好的產品方向，但必須先完成 ARMv7/PYNQ 實機 qualification。
- **Current / Accepted Policy** — [ADR-0002: IC Discovery、Catalog Level 與 Catalog 可見性統一政策](adr/0002-openocd-software-qualified-catalog-visibility.md)：所有 Manufacturer 使用 L0 `DISCOVERED` → L1 `PROGRAMMING_CANDIDATE` → L2 `PROGRAMMABLE` → L3 `PLASMA_VERIFIED`；L0 是 Internal Research Registry、一般 IC Selector 對客戶顯示 L1–L3 並提供 Level Filter、Job Picker 維持 L2/L3，L3 表示至少一組版本化 PLASMA configuration 已 HIL PASS。Active API/runtime 不保留 `phase1_*`／`phase2_*`／`phase3_*` 欄位。
- **Proposed** — [ADR-0003: Runtime FPGA Driver 與動態重新配置責任邊界](adr/0003-runtime-fpga-driver-reconfiguration-boundary.md)：UIO-first Driver 選型候選、單一 PPU FPGA Configuration Owner、Linux 無須 Reboot 的 Bitstream 切換；尚待 Z2 Kernel／UIO／Bridge 證據，不是 Accepted Contract。

## Operator

- **Current** — [Plasma Console Operator Guide](operator/plasma-console-guide.md)：PMode／EMode、Batch Summary、操作與異常復原。

## Engineering governance and execution paths

- **Current / PR #1167 merged, Issue #1168 F1-B HIL PASS** — [Path 2 受保護 Z2 Root Entry](development/path2-generic-fpga-image-loader.md)：沿用可信 Dispatcher、SWPC SSH／sudo Transport 與既有兩參數 `operation + source_sha` Root Entry；Entry 固定呼叫 `pl.hil.fpga_image_root`，不再使用 Stage/Profile。實機驗收僅涵蓋 Site 1 F1-B Download／Identity Test／Golden Restore，不代表 Blue Pill Flash 或其他 Programmer IP 通過。

- **Historical Gate 1 offline test / current guarded route separate** — [Path 2 Real Provider Integration](architecture/plasma-path2-real-provider-integration-gate1.md)：原始 Gate 1 僅驗證 BIT/BIN、跨 Trigger Lease 與離線故障注入；當前受控執行路徑改由已註冊的可信 Stage Transport 與 Z2 Root SHA256 Manifest 保護。每次實機操作仍須獨立核對授權、映像 Hash、AXI 與 Recovery 證據。\n

- **Historical offline coordinator contract** — [Path 2 Three-Stage Build / Download / Testing Coordinator](architecture/plasma-path2-three-stage-gate1.md)：記錄 Build、Download、Testing 獨立 Trigger、兩段預設關閉的自動銜接與離線 Adapter／Receipt 測試；當前硬體權限取決於獨立受控 Dispatcher／Stage Transport 與 Work Order 授權，不由 Orchestrator 測試授予。

- **Current after Gate 2 / Owner-approved Gate 1 design** — [PLASMA Three-Path Work Execution Model](development/plasma-three-path-execution-model.md)：Gate 1 由 ChatGPT 推薦並讓使用者選擇 Path 1（ChatGPT Direct Work）、Path 2（SWPC CLI Work）或 Path 3（SWPC Codex Work）；批准後在明確授權內自動執行，PR 準備妥當才請求 Gate 2 合併。包含三套流程圖、角色分工、Github Actions Dispatch 前提、證據／資安邊界與不需 PR 的純驗證任務。**這是規範，不代表通用 SWPC Dispatcher 已啟用或授權硬體操作。**

- **Current / Development Mode** — [Three Shared BLOCKING Decisions](development/development-blocking-policy.md)：Path 2／Path 3 共用授權與來源、Z2 實機安全／復原、真實回執三個核心阻擋邊界；移除重複檢查，但不繞過裝置安全條件。

## Architecture and contracts

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
- **Gate 1 / Source-only L2 提案（Draft、未合併）** — [STM32F103 Medium-density 非 LQFP 12 顆 exact-ICPN 資格擴展](architecture/stm32f103-medium-nonlqfp-l2-v9.md)：8 顆直接適用性、4 顆 TR 包裝等價；7 顆 VFQFPN36 命名／Geometry 缺口保留 L1，2 顆 R/RTR 特例排除。僅 OpenOCD 0.12.0 原始碼與 ST 原廠證據，不代表實體 HIL 或執行授權。
- **Design-input only** — [STM32F103VBT6 LQFP100 Socket Reuse](architecture/stm32f103vbt6-lqfp100-socket-v1.md)：第四個 ST exact-ICPN 延伸樣板；原廠 DS5319 x8/xB LQFP100 共用 100-pin 接腳、17 個必要接點（含 VREF+/VREF−）、NC 保護；VBT6 獨立綁定 128 KiB／128 頁 L2 幾何，且保留 V8 的 64 KiB 封裝契約，僅 Host-only 驗證，不宣稱 L3／HIL。
- **Design-input only** — [STM32F103V8T6 LQFP100 Socket Profile](architecture/stm32f103v8t6-lqfp100-socket-v1.md)：第三個 ST exact-ICPN 封裝樣板；以 LQFP100 原廠 100-pin map、VREF+/VREF−、5 組 VDD/VSS、NC 接點及 Host-only 負向測試定義獨立設計輸入；不宣稱 Socket/HIL/L3。
- **Design-input only** — [STM32F103RBT6 LQFP64 Socket Reuse](architecture/stm32f103rbt6-lqfp64-socket-v1.md)：在官方 x8/xB 封裝適用性證據下，共用 LQFP64 實體接腳，但將 STM32F103RBT6 的 128 KiB／128 頁 Flash geometry 獨立綁定；不宣稱 HIL、L3 或 execution。
- **Design-input only** — [STM32F103R8T6 LQFP64 Socket Profile](architecture/stm32f103r8t6-lqfp64-socket-v1.md)：第二個 ST exact-ICPN 封裝樣板；64-pin manufacturer-backed pin map、SWD/power/NRST contract 與 Host-only fail-closed tests，尚未宣稱 Socket/HIL/L3。
- **Current** — [Manufacturer Enrichment Coverage Framework v1](architecture/manufacturer-enrichment-coverage-v1.md)：定義 M0–M5 manufacturer enrichment coverage、逐 ICPN missing-dimension 投影、explicit exact-ICPN scope composition 與 fail-closed inheritance 規則；不授權 runtime 或 hardware readiness。
- **Current** — [Manufacturer Device Basic Profile v1](architecture/stm32f1-device-basic-profile-v1.md)：目前以 explicit family profiles 覆蓋 STM32F1／STM32F2／STM32C0／STM32G0／STM32G4／STM32U0／STM32U3／STM32L5／STM32H7RS／STM32WBA5X／STM32N6，共 1,622 個 Production exact ICPN；剩餘 3,007 個 ST exact ICPN 已完成 evidence review，但因 Product Selector/eStore 直接證據不足、衝突或無法無損映射至固定 M1 欄位而 fail-closed。IC Information 固定為 10 欄，所有 Basic Profile 與 Programming Profile、Memory Map、HIL 分離。
- **Current** — [STM32H5 Host-only Readback Guard v1](architecture/st-h5-host-readback-guard-v1.md)：190 顆 H5 合成讀值的安全邊界測試；失敗／fallback／不匹配一律阻擋，不代表實機燒錄資格.
- **Current** — [STM32C5 Host-only STLDR Source Guard v1](architecture/st-c5-host-loader-table-v1.md)：139 exact DFP／33 base-only 的離線 Loader 來源與 Tcl array 測試，不能執行燒錄.
- **Current** — [Versioned OpenOCD Provider Registry v1](architecture/openocd-versioned-provider-registry-v1.md)：將 Upstream／ST 來源與 x86／ARMv7 Artifact SHA-256 分離，沒有實機安裝證據不宣稱可燒錄。
- **Current** — [ICPN Backend Candidate Registry v1](architecture/icpn-backend-candidate-registry-v1.md)：H5／C5 合計 362 顆來源鎖定的唯讀候選資訊，與 Production Backend Mapping、燒錄資格分離。
- **Current** — [Device Support and Validation](architecture/device-support-validation.md)
- **Plan** — [Device Support / Hardware Execution / OpenOCD Architecture](architecture/device-support-hardware-openocd.md)：PoC 維持 PYNQ + Python；Production 將 Programmer Backend、stable Plasma HW API、UIO/MMIO/DMA/IRQ 與 PL protocol engine 分層，並避免 OpenOCD per-bit bit-banging。
- **Plan** — [IC Support Reusable Profile Architecture](architecture/ic-support-profile-architecture.md)
- **Current** — [IC Support Coverage Normalization](architecture/ic-support-coverage-normalization.md)：以 derived inventory 將 production exact ICPN 正規化為 Base Device、Programming Profile 與 backend readiness，避免把商業料號數量誤當成燒錄演算法數量。
- **Current** — [IC Support Runtime Resolver Foundation](architecture/ic-support-runtime-resolver.md)：定義 exact ICPN → reusable IC Support profiles 的 runtime-consumable resolver，並維持 Profile resolved 與 backend/runtime implemented 的 fail-closed 邊界。
- **Current** — [Profile-driven OpenOCD Plan Compiler](architecture/ic-support-openocd-plan-compiler.md)：將 evidence-backed Programming Profile 與 Memory Geometry 編譯成 deterministic OpenOCD dry-run plan；C8／CB geometry 分流，但硬體 execution 維持 fail-closed。
- **Historical baseline** — [OpenOCD Software Qualification v1](architecture/openocd-software-qualification-v1.md)：首批 C8/CB direct-reference qualification。
- **Historical expansion** — [OpenOCD Software Qualification v2](architecture/openocd-software-qualification-v2.md)：加入首批 C8/CB `TR=tape-and-reel` packing-only equivalence。
- **Historical expansion** — [OpenOCD Software Qualification v3](architecture/openocd-software-qualification-v3.md)：把 STM32F103 medium-density direct applicability 擴到 R8/RB/V8/VB T6，並只對已直接資格化的 T6 exact ICPN 展開 TR packing equivalence。
- **Historical expansion** — [OpenOCD Software Qualification v4](architecture/openocd-software-qualification-v4.md)：在 exact Production identity 與 DS5319 Flash characteristics 證據下，直接資格化 C8/CB/R8/RB/VB 的 T7 LQFP cohort，再對其 TR packing variant 做 deterministic inheritance；總計 22 個 exact ICPN SUPPORTED。
- **Historical expansion** — [OpenOCD Software Qualification v5](architecture/openocd-software-qualification-v5.md)：建立 multi-density umbrella authority，加入 STM32F103 high-density R-pin/LQFP bounded cohort，合計 31 個 exact ICPN SUPPORTED。
- **Historical expansion** — [OpenOCD Software Qualification v6](architecture/openocd-software-qualification-v6.md)：legacy Phase 命名文件；以現行術語解讀為 ST Level 0 identity set 維持 4,629 exact ICPN，41 個 exact ICPN 具 `SUPPORTED` qualification、可導出 Level 2 `PROGRAMMABLE`。
- **Current** — [OpenOCD Software Qualification v7](architecture/openocd-software-qualification-v7.md)：ST Level 0 identity set 維持 4,629 exact ICPN；49 個 exact ICPN 的 Programming Qualification 為 `SUPPORTED`，因此可導出 Level 2 `PROGRAMMABLE`；其餘 ICPN 的 L1 programming-candidate coverage 另由 route projection 決定；Level 3 `PLASMA_VERIFIED` 仍未宣告。
- **Current** — [OpenOCD Compiled-Plan Executor](architecture/ic-support-openocd-plan-executor.md)：驗證 PS-side canonical OpenOCD plan → isolated software subprocess boundary；production hardware gate 仍關閉，PL/native programming 不在本階段範圍。
- **Current** — [Vendor-neutral IC admission governance](architecture/vendor-neutral-ic-admission.md)：以 content-addressed artifact、review、disposition、canonical envelope、operation admission 與 backend binding 建立通用治理邊界；尚未接入 production runtime。
- **Current** — [IC Support Architecture Freeze v1](architecture/ic-support-architecture-freeze-v1.md)：凍結 PR-A／PR-B／PR-C／PR-D 後的 vendor-neutral trust、operation admission、Compiler Registry 與 software/hardware readiness 邊界；不宣稱 HIL 或實體燒錄 readiness。
- **Current** — [Mock Runtime v1.1](architecture/mock-runtime-v1.1.md)
- **Current** — [Mock Synthetic Image Contract](architecture/mock-synthetic-image.md)
- **Current** — [Optional Manager Control Plane](architecture/manager-optional-control-plane.md)
- **Current** — [Manager Read-only Fleet Aggregation](architecture/manager-readonly-fleet-aggregation.md)
- **Historical** — [Historical Multi-Programmer / Multi-Site Naming](architecture/multi-programmer-sites.md)

## Development and validation

- **Gate 1 / Path 3 / Phase A / Host-only** — [Blue Pill USB CDC Firmware v0.1 Evidence](evidence/blue-pill-usb-cdc-phase-a-20261023/README.md)：STM32F103C8T6 韌體編譯、ELF／HEX／BIN 靜態核對、Heartbeat／命令 Host 測試與 SHA256；實體 USB、LED、ST-LINK 與 Flash 均為 NOT_RUN，暫用 VID/PID 不是正式 PLASMA USB ID。
- **Gate 1 / Path 3 / Phase A / Code Review** — [Blue Pill USB CDC PR #1132 Review Repair Evidence](evidence/blue-pill-usb-cdc-pr1132-review-20261023/README.md)：Documentation CI 修復、連續 SEQ 與可選 Host Port 暫停測試、SWPC 重編譯與 SHA256；實體 USB 斷線與 HIL 仍為 NOT_RUN。

- **Development Mode / SWPC Monitor；實際工作執行驗收須逐次舉證** — [PLASMA Path 2/3 SSH tmux Monitor](development/plasma-engineering-ssh-tmux-monitor.md)：同一 tmux Window 並排顯示 Path 2 CLI 與 Path 3 Codex；閒置 IDLE、執行時 Run ID／即時進度、結束後 Exit Code。既有監看畫面可顯示兩個 Path，不代表已驗證特定 GitHub Run 的完整即時觀察；須以受授權工作的 Run ID、Log 與 Exit Code 個別確認 PASS／FAIL／NOT_RUN。本條目不設定 Path 3 的 Host-only 前置條件，也不授權部署或硬體操作。
- **Gate 1 / RCA archival closure (PR pending Gate 2)** — [PLASMA Path 3 Token Optimization RCA Closure](development/plasma-path3-token-optimization-rca-closure-2026-10-23.md)：固定 PR #1128 與兩次 SWPC 9×9 Run ID、Token/時間/81 成功率、Artifact SHA-256 與尚未完成的模型／Effort 因果歸因；Repo-first 工作流 DONE，逐請求 Token Attribution 保留低優先級技術債。
- **Gate 1 / Draft / Native Codex read-only bootstrap, SWPC NOT_RUN** — [Codex Native Read-only Preflight](development/plasma-codex-native-preflight.md)：沿用 Issue #981 與既有 Path 2 Dispatcher/Runner，新增固定 main-pinned、無模型 Session 的 Native ELF／SHA-256 唯讀盤點入口；未合併、未派工，不代表 PR #1135 已解阻。\n- **Gate 1 / Cross-Job Resume Candidate, SWPC NOT_RUN** — [Path 3 Cross-Job Resume Gate 1](development/plasma-path3-cross-job-resume-gate1.md)：沿用 Issue #981、既有 Dispatcher/Workflow/Runner，建立 CPU-only 雙 Job Resume 候選契約與負向測試；真實 SWPC 跨 Job 驗收尚未執行，不代表可合併或部署。
- **Gate 1 / CPU-only Path 3 Session Resume PoC (real Direct CLI Owner-reported PASS)** — [Path 3 Controlled Session Resume Host-only PoC](development/plasma-path3-session-resume-host-only-poc.md)：Fake Codex 離線測試 PASS；Owner 另於 SWPC 非特權隔離 Worktree 執行真實兩程序 NEW → FAIL → RESUME → PASS（同 Thread ID、專屬挑戰與修復驗證）；跨 GitHub Job 的正式 Path 3 Resume 仍 NOT_IMPLEMENTED／NOT_RUN。
- **Path 3 Repo-first instruction optimization / full normative reference** — [PLASMA Detailed Autonomous Development Contract](development/plasma-autonomous-development-contract-full.md)：完整保留原根目錄 AGENTS.md 的詳細規範；目前根目錄 AGENTS.md 為低於 Codex 預設 32 KiB 專案指令上限的精簡入口。針對實際任務按需讀取此完整條款，不代表 SWPC 已驗證載入來源或 Token 效率改善。
- **Gate 1 / Local-only Tool; Desktop Telemetry NOT_RUN** — [Codex Desktop vs Path 3 Token Usage Benchmark](development/codex-benchmark-usage.md)：針對 2026-10-22 9×9 測試，提供僅讀取指定本機 Session JSONL 的 Token 統計工具，區分單次 Turn、累計快照與 Path 3 Codex exec 用量；GitHub-hosted CI 使用合成資料，不代表已讀取 Mac Desktop 真實 Session，也不授權 SWPC、Z2 或 DUT。

- **Historical Gate 1 offline integration** — [Path 2 Runtime Integration Gate 1](architecture/plasma-path2-runtime-integration-gate1.md)：記錄當時的 Host-side Build Qualification、離線 F1-B Adapter／Lease 測試；目前有獨立的受控 Stage Transport。每次 Build／Download／Testing 仍須通過固定 Work Order SHA、映像 Hash、Sandbox 及硬體授權檢查。\n\n- **Historical offline Lease/Restore contract** — [Path 2 Persistent FPGA Lease and Restore Contract](architecture/plasma-path2-persistent-fpga-lease-gate1.md)：原始 Gate 1 以離線測試建立 Loaded State、Lease、Restore Intent、Timeout、不可盲目重試及 Testing 重入安全契約；是否執行實機操作由當前受控路徑與逐次授權決定。

- **Historical offline F1-B Adapter contract** — [Path 2 F1-B Adapter Integration](architecture/plasma-path2-f1b-adapter-integration-gate1.md)：原始 Gate 1 驗證 Vivado host-side Build、Hardware Profile、Supervisor、Test Callback 與離線 Mock／Schema 契約；當前受控 Stage Transport 的授權與證據檢查獨立成立。

- **Historical / Real Z2 Development PASS; AXI isolation UNPROVEN** — [F1-B Path 3 2026-10-20 Evidence](development/plasma-f1b-path3-39395142726-evidence.md)：紀錄 Run #39395142726 真實 FPGA Manager 單次 Load、三個 Identity readback、原始 base.bin Restore 的證據與開發風險邊界；不屬量產驗證。
- **Historical / Path 2 reference only** — [F1-B Codex As-run Steps and Path 2 Handoff](development/plasma-f1b-path3-39395142726-codex-steps.md)：保留 Codex 真實執行命令順序、故障修正與證據，供 Path 2 未來 Build／Download／Testing 獨立 Trigger 及可選階段銜接參考；不得直接重放一次性實機風險特例。
- **Path 2 guarded Z2 execution / historical handoff** — [Path 2 F1-B Z2 Three-stage Execution Handoff](development/plasma-path2-f1b-z2-execution-handoff.md)：現行可信路徑保留 Work Order 固定 SHA、映像 Hash、Z2 Root SHA256 Manifest 及 Download／Testing／Restore 逐次證據要求；歷史 NOT_RUN 不等於目前狀態，舊 Bridge/PIN 部署步驟已由受信任 Stage Transport 取代。

- **Plan / Host-only** — [Runtime FPGA Driver／Switching HIL Acceptance v1](development/runtime-fpga-switching-hil-plan-v1.md)：Phase 1 唯讀盤點、Phase 2 Driver HIL、Phase 3 Fault Injection、Phase 4 A/B Switching 的逐項 PASS／NO-GO 契約。
- **Current** — [Documentation Maintenance](development/documentation-maintenance.md)
- **Current** — [AI-assisted Git Workflow](development/ai-git-development-workflow.md)
- **Current** — [PLASMA GitHub Actions Control Bridge](development/plasma-actions-control-bridge.md)：定義 Issue #814、actor／workflow allowlist、`dispatch`／`cancel`／`rerun` 命令與最小權限安全邊界。
- **Plan / Pilot** — [PLASMA Codex SWPC Read-only Bootstrap](development/plasma-codex-pilot.md)：Issue #981 Gate 1 A 的安全派工、獨立 Worker、tmux 監控與驗收邊界；尚非正式部署。
- **Plan / Preflight** — [PLASMA Codex SWPC Bootstrap Preflight](development/plasma-codex-swpc-bootstrap-preflight.md)：Issue #981 的現有 SWPC Runner 唯讀前置檢查與真實 Worker 驗證邊界；未執行部署或硬體操作。
- **Plan / Host setup** — [PLASMA Codex SWPC Dedicated Worker Provisioning](development/plasma-codex-worker-provisioning.md)：Issue #981 獨立 Linux 帳號、tmux 監控目錄、Runner 註冊與安全驗證的分階段作業程序；文件與程式碼本身不代表 SWPC 已配置。
- **Plan / Passive inventory** — [PLASMA Codex Direct HIL Tool Readiness](development/plasma-codex-hil-tool-inventory.md)：重用 Z2 SSH／UART／JTAG、Hub 直接 USB 命令及 KINGST LA Driver／CLI，僅盤點專用 Worker 的 PATH、USB 列舉與裝置權限，不開啟或操作設備；Gate 2 前不觸發實機盤點。
- **Plan / Host activation** — [PLASMA Codex Hardware Access Parity](development/plasma-codex-hardware-parity.md)：複製原 Codex 經驗證的 Z2／Hub／KINGST 所需 Linux 裝置權限及已鎖定 sigrok AppImage；僅由 SWPC 受信任管理員在 Gate 2 後啟用，保留原設備權限與兩階段合併審核。
- **Plan / HIL smoke** — [PLASMA Codex Z2 SSH／UART Login + Live tmux](development/plasma-codex-z2-login.md)：使用現有 SWPC 專用 Runner 執行受控、限時的實機 SSH／UART 登入驗證，支援 SWPC tmux 即時監看；不公開帳密、私有位址或原始 UART 資料。
- **Plan / HIL readiness** — [PLASMA Codex Z2 SSH-only PS/PL Readiness](development/plasma-codex-z2-readiness.md)：重用已實機通過的 SSH 通道、唯讀觀察 Z2 Linux／FPGA Manager／FCLK／UIO／Driver／服務狀態，獨立記錄尚未符合的 HIL 條件；不執行 FPGA 重載、MMIO 或 DUT 操作。
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
