# Plasma Documentation Index

本頁是 `docs/` 的 canonical 文件入口。執行中的程式、設定 schema、REST／wire contract 與自動測試優先於描述性文字；若兩者不一致，先停止操作、以實作與測試確認事實，再在同一個變更中修正文檔。

## 文件狀態

每個條目以 ``- **狀態** · `標籤` — 連結：說明`` 表示（標籤可為零到多個）。狀態只能是下列四種之一；Gate／Path／硬體結果／來源 PR 等資訊放在狀態後的標籤，不寫進狀態。

| 狀態 | 意義 |
|---|---|
| **Current** | 描述目前已實作或目前必須遵守的契約。 |
| **Reference** | 設計背景、工作紀錄、驗證邊界或維護方式；不得取代 Current contract。 |
| **Plan** | 尚未全部實作的核准方向；不能宣稱為現有能力。 |
| **Historical** | 已淘汰或被取代，僅供背景；不是相容性或執行契約。 |

## 治理：從這裡開始

- **Current** — [Root AGENTS.md — primary operating contract and domain routing](../AGENTS.md)
- **Current** — [Shared Development Contract — shared clauses, execution zones, domain routing](development/plasma-development-common.md)
- **Current** — [Path 2 SWPC CLI Contract — guarded-hardware operator-cli, CPU-only and Vivado host build](development/plasma-path2-cli.md)
- **Current** — [Path 3 SWPC Codex Contract](development/plasma-path3-codex.md)
- **Current** — [FPGA / PL domain contract](development/plasma-fpga.md)
- **Current** — [Embedded / Z2 PS domain contract](development/plasma-embedded.md)
- **Current** — [Manager / Gateway / backend domain contract](development/plasma-manager.md)
- **Current** — [Web UI domain contract](development/plasma-web.md)
- **Current** — [Former monolithic contract — entry stub linking the contracts above](development/plasma-autonomous-development-contract-full.md)
- **Current** — [Documentation maintenance rules — statuses, placement, source priority](development/documentation-maintenance.md)
- **Reference** · `OPF Bundle v3` · `Host-only Gate 1` — [User Bundle v3 Source-independent Admission Evidence](development/opf-user-bundle-source-agnostic-host-20261106.md)：記錄移除使用者 Bundle Git Source/Publisher 資格限制的 Host-only 實作與測試；新 Z2 B3 仍未實測。
- **Plan** · `Owner approved 2026-11-09` · `Gate 1` — [OPF Local Owner Mode 授權呼叫鏈稽核與分階段遷移](development/opf-local-owner-mode-gate1-20261109.md)：以最新 main 確認現有 Registry、Bootstrap Token、BFF Cookie、HMAC、PPU 安全守門，提出本機接管與失憑證恢復設計；只做 Host-only 基準測試，不改執行路徑。
- **Plan** · `Claude Code handoff` · `no implementation` — [OPF Local Owner Mode Claude 完整工作包](development/opf-local-owner-mode-claude-handoff-20261109.md)：D1–D8 技術決策、P2A/P2B/P1/P3/P4 的 PR 分解、程式修改候選、正負向驗收、網路／硬體停止條件；尚未交由 Claude 執行。
- **Current** — [Glossary — current terms and retired codes](glossary.md)

## Architecture Decision Records

- **Current** — [ADR Index](adr/README.md)：所有 ADR 與其 Proposed／Accepted／Superseded 狀態。
- **Current** — [ADR-0001: PYNQ System Python 與 Plasma PPU Runtime 分離](adr/0001-pynq-system-python-plasma-runtime-separation.md)：PYNQ owns System Python；Plasma owns an isolated, Plasma-qualified Python runtime。Bundled Python 是偏好的產品方向，但必須先完成 ARMv7/PYNQ 實機 qualification。
- **Current** — [ADR-0002: IC Discovery、Catalog Level 與 Catalog 可見性統一政策](adr/0002-openocd-software-qualified-catalog-visibility.md)：所有 Manufacturer 使用 L0 `DISCOVERED` → L1 `PROGRAMMING_CANDIDATE` → L2 `PROGRAMMABLE` → L3 `PLASMA_VERIFIED`；L0 是 Internal Research Registry、一般 IC Selector 對客戶顯示 L1–L3 並提供 Level Filter、Job Picker 維持 L2/L3，L3 表示至少一組版本化 PLASMA configuration 已 HIL PASS。Active API/runtime 不保留 `phase1_*`／`phase2_*`／`phase3_*` 欄位。
- **Historical** · `superseded by ADR-0004` — [ADR-0003: Runtime FPGA Driver 與固定映像候選責任邊界](adr/0003-runtime-fpga-driver-reconfiguration-boundary.md)：UIO-first Driver 選型候選、單一 PPU FPGA Configuration Owner、Linux 無須 Reboot 的 Bitstream 切換；尚待 Z2 Kernel／UIO／Bridge 證據，不是 Accepted Contract。
- **Current** — [ADR-0004: FPGA Image lifecycle and programming-flow loading](adr/0004-fpga-image-lifecycle-and-job-driven-loading.md)：Image＋Manifest 配對、Keep Loaded、Golden 僅於明確選擇或故障時還原；Console 決定 FPGA Package 傳送，進入燒錄流程時由 PS FPGA Hardware Manager 載入所需 bitstream（尚未實作）。

- **Plan** · `PR #1189 pending` — [ADR-0004: 新 FPGA Project 與 Path 2 operator-cli 標準](adr/0004-project-isolated-fpga-build-path2-operator-cli.md)：新 FPGA Image 與 Board target 各自擁有獨立、可重現的 Vivado Project；SWPC 正式 Host Build 透過 SHA-pinned Path 2 `operator-cli`；Build 不是部署。
- **Historical** · `superseded by ADR-0006` — [ADR-0005: 獨立 SWD IP 與原 SWD Debug Bitbang 提案](adr/0005-independent-swd-ip-guarded-bitbang.md)：僅供歷史決策追溯。
- **Plan** · `PR #1189 Draft` — [ADR-0006: 專用 SWD Engine 與未來通用 GPIO Bus](adr/0006-independent-swd-engine-and-future-gpio-bus.md)：SWD 只保留 OFF/NORMAL，未來 GPIO Bus、JTAG、SPI、UART、I²C 分別規劃，未宣稱實作或實機驗收。
- **Plan** · `Host-only` — [ADR-0007: PPU Image/Reload 與每 Site 並行所有權](adr/0007-ppu-reload-fence-per-site-locking.md)：保留 Root Guard，PPU Fence 共享／獨占及每 Site 獨占鎖；不宣稱 Z2 或 8-Site HIL。
- **Plan** · `Accepted policy 2026-11-09` · `not implemented` — [ADR-0008: PLASMA PPU Local Owner Mode](adr/0008-local-owner-mode.md)：使用者離線自主設定、安裝與燒錄，不需帳號／License／原廠操作授權；須經本機控制權建立且保留完整硬體與交易安全檢查。

## PPU architecture and runtime

- **Current** · `PR #1343/#1348 Merged` · `S0–S5 partial` — [PLASMA Core Convergence and Deletion-First Roadmap](architecture/plasma-core-convergence-and-deletion-first-roadmap.md)：後續 OPF／Bundle／Runtime 收斂及舊程式刪除的共同基準；S0–S5 尚待個別 Gate 1，非 Runtime 或實機驗收。
- **Reference** · `S5-A Gate 1` · `Host-only` — [OPF S5-A bounded source convergence and import-boundary regression](development/opf-s5a-source-convergence-gate1-20261108.md)：記錄可攜式 OPF 隔離匯入、故意注入相依的負向測試、退休 Compiler 防回流、既有路由與安全邊界；僅 Source-only，不是 S5 Final Closure 或實機驗收。
- **Reference** · `S5-B Gate 1` · `Host-only` — [OPF S5-B final architecture convergence](development/opf-s5b-final-convergence-gate1-20261109.md)：PPU Gateway 相容 Device Selector 路由刪除後的 Consumer 稽核、刪除／保留清單、Import Graph、LOC 與 Runtime Footprint；僅 Host-only，HIL NOT_RUN。
- **Plan** · `Gate 1` · `Host-only` · `Draft` — [Console-driven Bundle Programming](development/console-bundle-programming-gate1-20261109.md)：User 於 Console 選 IC／Firmware／PPU／Site 後，由 Manager 以共用 `plasma_opf.bundle_v3` 建立 Canonical Bundle v3，Active Set 不同時才走既有 B1/B2/B3，再送出單次 `flash_cycle` 並驗證 Readback／Verified Bytes／SAFE_OFF；UNKNOWN 不重送。僅 Host-only，實機 NOT_RUN。
- **Plan** · `Gate 1` · `Host-only` · `Draft` — [Catalog L3 independent PPU Ready / Socket Ready and PM0075 Family Ready](development/catalog-l3-independent-readiness-gate1-20261109.md)：STM32F103 共 77 顆 L3（1 顆 Direct HIL、76 顆 Family Ready，ST PM0075 Rev 2、OpenOCD `stm32f1x.cfg`）；Family Ready 不是逐顆實機 PASS，Socket Ready 獨立且 NOT_TESTED；不授權執行。
- **Current** · `Bundle v3` · `PR #1225` — [Canonical Bundle v3: Bundle → Packages → Files](architecture/ppu-canonical-bundle-packages.md)：`packages[]`、Package DAG、SHA256 Admission；v1/v2 舊格式不作為 v3 相容介面。Site 2 Bundle A/B 已有實際 B1/B2/B3 與 Flash 驗收證據；其他 Host/Site 未驗證。
- **Plan** · `PR #1225` — [PPU Target Platform Identity](architecture/ppu-target-platform-identity.md)：`linux-armv7` 可信套件目標與 `linux-armv7l` runtime 觀測值的區分；不得視為已證實的 HTTP 409 根因。
- **Current** · `OPF-3A` · `PR #1303 Merged` · `Host-only + Site 2 integration` — [OPF Per-Site Session Ownership](architecture/opf-site-session-manager-gate1.md)：重用既有 C-3 Worker、PPU Lease、ADR-0007 Lock／Fence；Site 2 已有新路徑 Flash PASS，但不同 Site 真正並行仍未驗證。
- **Current** · `OPF-3B` · `PR #1307 Merged` — [Provider Route / Site Session / Job Timeout Integration](architecture/opf-3b-provider-site-session.md)：將 Provider Route 綁定同一 C-3 Session 與 Job Deadline；已在後續 S1-C／S2 合併實作中取得單 Site Flash HIL，不推論跨 Site。
- **Plan** · `P1-01` · `Host-only` — [OPF Provider-owned Options Schema](architecture/opf-provider-options-schema-gate1.md)：在同一 Active Asset Set 內以版本化宣告式 Schema 驗證已選 Provider 的 options，綁定 Schema／Options SHA；不執行 Provider、不切換 Runtime 或操作硬體。
- **Current** · `PR #1301 Merged` · `Host-only` — [OPF Provider Capability / Bundle Resolver](architecture/open-provider-framework-gate1.md)：單一可信 Bundle v3 Active Asset Set 內的 Provider／Profile／PS-only／FPGA capability 解析；尚未接入正式 Runtime、Z2 或 DUT，Timeout 統一由 OPF-1 決定。
- **Current** · `OPF-1` · `PR #1302 Merged` · `standalone Linux Host-only` — [Open Provider Framework (OPF) architecture](architecture/opf-architecture.md)：共用 Provider／Profile／Options／Result 契約；獨立 Linux Python Provider 仍僅 Host-only，PPU OpenOCD 路徑已具單一 Site 實機證據。
- **Current** · `OPF-4A` · `merged Reference Provider` · `Site 2 HIL PASS` — [OpenOCD / ABI v5 Reference Provider](architecture/opf-4a-openocd-reference-provider-gate1.md)：已驗證 C-3 經 Bundle v3 選擇 OpenOCD Provider；Bundle A/B 各一次 Site 2 Flash／Readback／SAFE_OFF PASS，不涵蓋其他 Provider。
- **Reference** · `Site 2` · `PR #1337 Merged` · `Host-only` — [OPF platform-provider Bundle v3 source alignment](development/site2-opf-platform-bundle-v3-gate1.md)：Gen7 舊 Engine reference 拒絕原因、原始 Builder 來源缺口、替代離線 Builder 與正負向測試；未部署 Z2、未操作 DUT。
- **Reference** · `Site 2` · `PR #1338 Merged` · `read-only tool` — [PPU Deployment Doctor（Z2 backend）](deployment/plasma-ppu-doctor.md)：唯讀診斷入口保留；此文的 Gen7 Joint Acceptance 為歷史範圍，最新 Bundle v3 A/B 實機結果另見當日 evidence。
- **Current** · `Programming CLI` · `S1-C/S2` · `Site 2 A/B HIL PASS` — [通用 Bundle v3 燒錄 CLI](deployment/plasma-program-cli.md)：已透過既有 Bootstrap B1/B2/B3 與 Runtime Bundle Job 完成 A/B 各一次實機 Flash、完整 Readback 與 SAFE_OFF；只證明單一 Site／IC，不是八通道驗收。
- **Reference** · `Site 2` · `2026-11-07` · `real Flash PASS` — [Site 2 首次真實 Flash 固定證據](evidence/site2-first-flash-2026-11-07/README.md)：含來源 SHA、Job ID、Readback SHA256、SAFE_OFF、Runtime／OpenOCD identity 及受控復原回執；只證明一顆 STM32F103C8T6 / Site 2。
- **Historical** · `2026-11-08 pre-HIL snapshot` · `merged #1350` — [OPF S2 Site safety source audit](evidence/opf-s2-s1c-site2-hil-audit-2026-11-08.md)：保留當時 C-3 未分類例外與 Fail-Closed 的來源稽核；其中 `NOT_RUN` 是歷史時點，不是今日現況。
- **Reference** · `2026-11-08` · `Site 2 A/B real HIL PASS` — [OPF S1-C/S2 Bundle A/B new-path physical evidence](evidence/opf-site2-ab-newpath-2026-11-08.md)：兩份 Bundle v3 各自啟用／單次 Flash 完整 Readback SHA256 與 SAFE_OFF，含 Path 2 Job/Transaction 證據。
- **Reference** · `2026-11-09` · `Catalog-free Runtime + Site 2 A/B real HIL PASS` — [Post-S5 Runtime `a1b1c6f3b` 更新與 Bundle A/B 重跑](evidence/opf-site2-ab-catalog-free-runtime-2026-11-09.md)：單次 Coordinator Runtime 更新後，A／B 各一次 Flash、完整 Readback SHA256 與 SAFE_OFF；Active 現為 Bundle B，Control Station 尚未更新。
- **Reference** · `2026-11-09` · `Console Bundle Programming real HIL PASS` — [Console-driven Bundle Programming 首次實機](evidence/console-bundle-programming-hil-2026-11-09/README.md)：Z2 Site 2、v0.1 Image；H1 經 Console BFF（非人工 UI）需啟用 B1/B2/B3 → 單次 `flash_cycle` PASS；H2 Owner 真實 Console UI（Already Active）PASS；attempts=1、Readback 相符、SAFE_OFF true；Active Set 由 H1 B3 `d929e985…` 自 Bundle B（gen 12）切換為 `4d2837d4…`（gen 13）。人工 UI Cache-Miss 路徑實機未驗。
- **Reference** · `PR #1353 Merged` · `S2/S3 bounded deletion` — [OPF S2/S3 bounded convergence ledger](development/opf-s2-s3-convergence-gate1-20261108.md)：刪除重複的舊 Site2 Flash 路徑、保留 PPU Lease、C-3 Site Session、Root/FPGA Ownership 與單一 Bootstrap Coordinator；其他 S2/S3 範圍尚待個別驗證。
- **Plan** · `S2/S3/S5` · `Gen7 retirement Gate 1` — [Gen7 Site 2 helpers retirement ledger](development/opf-s2-s3-s5-gen7-retirement-gate1-20261108.md)：遷移 Active 唯讀觀測、刪除已取代的 Gen7 B3/Joint 工具與測試，保留完整 PPU Site/FPGA/Recovery 權限與獨立 Bundle Builder；此 Draft 清理不代表部署或 HIL。\n- **Plan** · `Owner decision 2026-11-04` · `PR #1298` — [Unified Bundle-driven Programming Execution](architecture/unified-bundle-driven-programming-decision-2026-11-04.md)：Engineering／Production 共用同一條燒錄執行流程（其他政策不變）；Bundle 自帶 IC Profile／Provider／Driver／FPGA，Catalog 與固定 ICPN／Compiler／Image 登錄不得阻擋執行，保留必要來源、相容性及硬體安全驗證。目標架構尚未完整實作。
- **Plan** · `Owner decision 2026-11-02` · `not implemented` — [PPU Single Active Asset Set：Bundle = Assets，Controller 指定整份資源與操作](architecture/ppu-job-driven-package-resolution.md)：每台 PPU 同時只有一份 Active Asset Set；Console 比對完整 Asset Set SHA256，若不同即傳送整份 Set；B1/B2/B3 負責 Receive／Admission／Install-Verify，但不自動啟用、載入 FPGA 或燒錄。Controller 決定 FPGA Image／Programming Profile 與 E/P/V/R；PPU 只在 Active Set 內選擇資源並驗證能力。Active+Staging 隔離、Job 執行期間不可切換、FPGA 配置是獨立受控操作。介面／B4／實機尚待實作。
- **Reference** · `Host-only` · `PR #1208` — [PPU Master 非 Root 受控執行與部署契約](architecture/ppu-master-nonroot-execution-gate1.md)：重用既有 PPU Installer/Bootstrap 與 Root Guard，建立 WordPort／FPGA／Protected Root 的特權操作規劃與正負向測試；不接入真實權限、不改 Z2、不部署、不合併。
- **Plan** · `Host-only` · `product policy` — [PPU Z2 Monitor/Master/Engineer Privilege Boundary](architecture/ppu-privilege-boundary-gate1.md)：PPU 三級產品能力、Master 非 Linux Root 操作與部署、Engineer Root 維修、特權 Bridge 的預期邊界；僅 Host-only policy／tests，尚未接入 Runtime／Z2。
- **Reference** · `Runtime` · `DEFAULT OFF` — [Reusable Engineering Runtime Dispatcher v1](architecture/plasma-engineering-runtime-dispatch-v1.md)：Path 2 SWPC CLI／Path 3 SWPC Codex 共用 Work Order、Capability、SHA 與一次性保護 Claim；PR 與 push 僅執行 GitHub-hosted 離線測試。尚未啟用 SWPC 執行，隔離 Runner／自動 Gate 1 Dispatch／真實 Publisher 未驗收，不代表可操作任何實體硬體。
- **Current** — [Facility / PPU / Site Domain Model](architecture/ppu-facility-sites.md)
- **Current** — [PPU Execution Ownership](architecture/ppu-execution-ownership.md)
- **Current** — [Domain Naming and Identity Policy](architecture/domain-naming-migration.md)
- **Current** — [Web Product Modes](architecture/web-product-modes.md)
- **Current** — [Web REST API Contract](architecture/web-rest-api-contract.md)
- **Current** — [Configuration Architecture](architecture/configuration-architecture.md)
- **Current** — [PPU Site Configuration](architecture/ppu-site-configuration.md)：定義 Phase 1 `enabled`／`interface`／`target` desired state、PPU authoritative validation、canonical YAML atomic persistence、active-execution write gate、desired／actual reconciliation 與 Manager/BFF allowlist 邊界。
- **Current** — [CI/CD Validation Architecture](architecture/ci-cd-validation-architecture.md)：定義 risk-based validation topology、Fast／Browser／Runtime／Release gate、Device Catalog Historical／Current 邊界，以及 production Device Catalog → IC Support 的跨 domain dependency。
- **Current** — [Batch Domain Model](architecture/batch-domain-model.md)
- **Current** — [Server-side Batch Runtime](architecture/server-side-batch-runtime.md)
- **Current** — [Batch Persistence and Gateway Restart Recovery](architecture/batch-persistence-recovery.md)
- **Current** — [Plasma Gateway Communication and Recovery](architecture/gateway-communication-recovery.md)
- **Current** — [PPU Network Configuration](architecture/ppu-network-configuration.md)：定義 Phase 1 `eth0` desired-state API、Default Gateway／DNS 等 Linux network 參數、驗證、持久化與 Phase 2 activation／reconnect／rollback 邊界；並區分 Plasma Gateway service 與 Linux Default Gateway。
- **Reference** — [Virtual PPU Network Lab](architecture/virtual-ppu-network-lab.md)：以 Linux host 上的 production Plasma Manager 驅動兩個 isolated packaged ARMv7 Virtual PPU，驗證 real managed-IPv4 migration、same-`ppu_id` reconnect、activation commit、Manager registry CAS／journal 與 privilege separation；不代表 PYNQ-Z2 native network backend acceptance。
- **Reference** — [Static IPv4 Fault Injection](architecture/static-ipv4-fault-injection.md)：在 fresh isolated Virtual PPU topology 注入 duplicate candidate、wrong `ppu_id`、reconnect timeout、helper failure 與 Manager pre/post-commit crash，驗證 rollback、`recovery_required`、registry fail-closed 與 restart reconciliation；不代表 PYNQ-Z2 native network backend acceptance。
- **Current** — [Production Real-Path Loopback Diagnostics](architecture/diagnostics-real-path-loopback.md)
- **Current** — [Control Plane Routing Architecture](architecture/control-plane-routing-architecture.md)：定義 Control Console、BFF、Plasma Manager、Plasma Gateway、Plasma Server 的責任邊界，以及 Managed Mode 的 Programming／Loopback 共用 production route。
- **Current** — [Manager Runtime PPU Registry](architecture/manager-runtime-ppu-registry.md)：定義 Manager-owned runtime inventory、Plasma Gateway Endpoint、`pending`／`commissioned`／`disabled` lifecycle、Add／Validate & Enable／Disable／Remove 與 durable state 邊界。
- **Reference** — [Remote Write Security Boundary](architecture/remote-write-security-boundary.md)
- **Current** — [PMode Factory Console v2](architecture/pmode-factory-console-v2.md)
- **Current** — [Engineering Programming Workspace](architecture/engineering-programming-workspace.md)
- **Current** — [Engineering Programming Observability](architecture/engineering-programming-observability.md)
- **Current** — [Engineering Settings UI Design System](architecture/engineering-settings-ui-design-system.md)
- **Plan** — [Installed OpenOCD Evidence Root v1](architecture/runtime-evidence-root-implementation-v1.md)：修正 source-only H5/C5/OpenOCD Provider 顯示資訊在非 editable Python 安裝下的路徑解析，區分 Render full 與 Slim PPU 必備／可省略來源；不授權燒錄。
- **Current** · `CI` — [Runtime Data Root Contract v1](architecture/runtime-data-root-contract-v1.md)：所有可安裝 Python 模組使用明確 Data Root，AST CI 禁止新增 wheel `__file__` 相對路徑推算；只保留 2 個受控 Source-tree 開發例外，並守護 NXP、OpenOCD 與 KL25 Root Resolver。
- **Current** — [Vendor-neutral IC admission governance](architecture/vendor-neutral-ic-admission.md)：以 content-addressed artifact、review、disposition、canonical envelope、operation admission 與 backend binding 建立通用治理邊界；尚未接入 production runtime。
- **Current** — [Mock Runtime v1.1](architecture/mock-runtime-v1.1.md)
- **Current** — [Mock Synthetic Image Contract](architecture/mock-synthetic-image.md)
- **Current** — [Optional Manager Control Plane](architecture/manager-optional-control-plane.md)
- **Current** — [Manager Read-only Fleet Aggregation](architecture/manager-readonly-fleet-aggregation.md)

## PL / FPGA, Z2 PS hardware path and HIL

- **Reference** · `Host-only` · `PR #1202` — [Root Guard 燒錄 Session 與 FPGA Configuration 准入分離](development/root-guard-runtime-program-split-2026-10-29.md)：正常燒錄取消全系統 `/proc` FD／VMA 完整掃描，保留裝置限定 `fuser`、全域 FPGA 鎖、Image／Boot／UIO Guard；FPGA Download／Test／Restore 持續嚴格掃描。尚未部署、合併或實機驗收，亦非八通道 Broker 已完成。
- **Reference** · `source audit` · `PR #1205` — [Z2 Root Guard Rule Necessity Audit](development/z2-root-guard-rule-audit-gate1.md)：逐項核對 Root Guard、Source Pin、UIO／MMIO Owner、/proc 掃描、PPU Reload Fence、Job Lease 與 UNCERTAIN，標明必要保留、維護專用、重複候選及尚未合併的 Draft；本次不刪除受保護程式。
- **Plan** · `documentation-only` · `M1 NO-GO` — [PLASMA Verification Platform v1](architecture/plasma-verification-platform-v1.md)：統一 FPGA SIM-0～SIM-4 的工具與平台、PS Driver→AXI→RTL 驗證矩陣、可信任 SWPC 邊界及未來證據格式；本 PR 不變更 CI 或授權任何硬體操作。
- **Historical** · `retired 2026-11-02` — [Unified FPGA Build & Diagnostic Engine v1.0](architecture/plasma-unified-fpga-build-diagnostics-v1.md)：Path 2／Path 3 共用 Vivado Driver、階段式錯誤診斷、License／目錄前置檢查、SHA256 Artifact；本次僅驗證離線測試，未在 SWPC 重新建置，硬體 M1 NO-GO。
- **Reference** · `Unified AXI` · `M1 NO-GO` — [Fixed PPU Unified 64KiB AXI Site1](architecture/fixed-ppu-unified-axi-site1-gate1.md)：AXI AW/W 配對、Identity + Site1 同一入口、Global Fault 連動及虛擬 SWD E2E；Host-only，尚未實機驗證。
- **Reference** · `PPU Identity` · `M1 NO-GO` — [PPU Global Identity & Resource Admission](architecture/fixed-ppu-global-identity-resource-admission-gate1.md)：隔離 AXI-Lite Identity、Host-only Board Descriptor／UIO Resource Discovery／Broker Site 准入與負向測試；未授權真實硬體。
- **Reference** · `Semantic Convergence` · `M1 NO-GO` — [Fixed FPGA ABI v1 SWD Semantic Convergence](architecture/fixed-fpga-swd-semantics-gate1.md)：SWD 64-clock Reset、半週期、ACK／Error、FAULT ACK、Sequence／Driver 競態；Host-only，尚未實機驗證。
- **Reference** · `Simulation-only` · `M1 NO-GO` — [Fixed FPGA SWD Site 1 RTL Vertical Slice](architecture/fixed-fpga-swd-site1-rtl-gate1.md)：隔離的 AXI-Lite／SWD Site 1 RTL 與模擬 Driver，Cocotb 虛擬 DPIDR 測試；不代表實體 FPGA／UIO／八通道已驗收。
- **Reference** · `Fixed Image M1 NO-GO` — [Zynq-7020 Universal Fixed Image ABI v1](architecture/fixed-fpga-hardware-abi-v1-gate1.md)：以 SWD／SPI PIO 定義完整最小 Command／FIFO／Site 1–8／Response 契約；[機器可驗證 ABI](../pl/verification/fixed_image_abi_v1_gate1.json) 為提案，**RTL 尚未實作**。
- **Reference** · `Host-only` — [Fixed Image UIO Driver Contract](development/fixed-fpga-uio-driver-contract-gate1.md)：依 Kernel／Device Tree／Physical Resource 唯一辨識 UIO，而非固定 uio0；不授權真實 /dev/uio*。
- **Reference** · `Host-only` — [Single Hardware Broker + Eight-Site Ownership](architecture/fixed-fpga-hardware-broker-eight-site-gate1.md)：Execution Owner／Hardware Broker／Site Lease／獨立 DUT Power Reset 分工。
- **Reference** · `M1 NO-GO` — [Fixed FPGA M1 Freeze Acceptance](architecture/fixed-fpga-m1-gate1-acceptance.md)：技術缺口、RTL/Driver/電氣驗證及下階段分工。
- **Plan** · `dynamic switching roadmap` — [Runtime FPGA Architecture v1.0](architecture/runtime-fpga-architecture-v1.md)：記錄一台 PPU 同批次相同 IC、多 Site 獨立執行、切換介面不重啟 Linux 的架構前提，以及 Driver／Hardware ABI／動態 FPGA Switching、HIL Phase、相依性與 Gate 邊界；**尚未實作，也不授權實機操作**。
- **Reference** · `early runtime-switching ABI proposal` — [Runtime FPGA Hardware ABI v1](architecture/runtime-fpga-hardware-abi-v1.md)：定義 PPU 64-KiB／8-Site 候選 AXI Map、Identity／Capability、Major/Minor，相容性與現有 MS01 的語意落差；**不代表真實 RTL 已實作**。
- **Reference** · `Host-only review` · `M1 NO-GO` — [Zynq FPGA Manager Isolation and Runtime Ownership Review](architecture/zynq-fpga-manager-isolation-ownership-review.md)：以 Z2 唯讀盤點、Kernel/DT 綁定與明確標示的 Xilinx 參考原始碼，審查 UIO Ownership、PS–PL 隔離缺口及 PPU Configuration Owner；不授權 FPGA 載入或 HIL-B/C。
- **Reference** · `Host-only evidence review` · `M1 NO-GO` — [PPU Phase 2B M1 Hardware Boundary](architecture/ppu-phase2b-m1-hardware-boundary.md)：以唯讀 UIO/Manager/Bridge Inventory 的離線 Gate 拒絕未經證實的 FPGA 重配置安全主張，列出 Kernel Source、AXI Drain、DMA/VMAs 與外部復原的硬體阻擋證據；不授權實機操作。
- **Plan** · `Host-only` — [Runtime FPGA Driver／Switching HIL Acceptance v1](development/runtime-fpga-switching-hil-plan-v1.md)：Phase 1 唯讀盤點、Phase 2 Driver HIL、Phase 3 Fault Injection、Phase 4 A/B Switching 的逐項 PASS／NO-GO 契約。
- **Plan** · `HIL smoke` — [PLASMA Codex Z2 SSH／UART Login + Live tmux](development/plasma-codex-z2-login.md)：使用現有 SWPC 專用 Runner 執行受控、限時的實機 SSH／UART 登入驗證，支援 SWPC tmux 即時監看；不公開帳密、私有位址或原始 UART 資料。
- **Plan** · `HIL readiness` — [PLASMA Codex Z2 SSH-only PS/PL Readiness](development/plasma-codex-z2-readiness.md)：重用已實機通過的 SSH 通道、唯讀觀察 Z2 Linux／FPGA Manager／FCLK／UIO／Driver／服務狀態，獨立記錄尚未符合的 HIL 條件；不執行 FPGA 重載、MMIO 或 DUT 操作。
- **Reference** · `Gate 1 retirement` · `Host-only` — [Z2 SWD-05 Legacy Dedicated Dispatch Retirement](development/plasma-z2-swd05-legacy-retirement-gate1.md)：退役 Issue #981 既有專用派工 Workflow／SWPC CLI／歷史 Route；保留 SWD-05 Linux Driver、原本受保護的 FPGA Owner Lock 與 Path 2／3 執行介面，不代表 SWPC 或 Z2 已執行清理。
- **Reference** · `Host-only reference review` · `M1 NO-GO` — [PPU Phase 2C: Z2 Kernel Source Lineage and AXI Isolation](architecture/ppu-phase2c-z2-kernel-source-lineage-axi-review.md)：釘選 Xilinx 2024.1 參考驅動 Git Blobs，分離 Z2 目標 Kernel/DTB 未匹配來源事實，審查 Manager 與 Region 的不同隔離路徑；不授權實機載入。
- **Reference** · `read-only inventory` — [Z2 Kernel/Device Tree Read-only Inventory](development/z2-kernel-dt-readonly-gate1.md)：限定唯讀 Kernel Config、Device Tree、FPGA Manager／Region／Bridge 與 UIO metadata；Host 假資料驗證與獨立 SWPC Codex 實機取證分開，M1 維持 NO-GO。
- **Current** — [FPGA Development Guide](development/fpga-development-guide.md)
- **Current** — [FPGA Verification Guide](development/fpga-verification-guide.md)
- **Reference** · `Host-only` · `M1 NO-GO` — [V2 PS Driver → AXI BFM → Fixed ABI Site-1 RTL Verification](development/fixed-abi-v2-ps-pl-host-verification-gate1.md)：固定 ABI v1 單 Site RTL 的真實 AXI 模擬失敗案例、可重現工具版本與未涵蓋的實體 PS／PL 邊界。
- **Current** — [PLASMA FPGA SystemVerilog Coding Standard](development/fpga-systemverilog-style.md)：規範新 RTL 的可移植語法、FSM／Type／Width、AXI/Response 與 SWD／Programming Site 驗證標準。
- **Reference** · `Operator-observed` · `HARDWARE NO-GO` — [2026-10-15 PYNQ-Z2 HIL Hardware Inventory](development/hil-hardware-inventory.md)：記錄 Transcend Hub Port 2／3／4、Z2 JTAG／UART 與 5V 供電主張、AX88179、KINGST LA2016、PL 執行環境及復原驗收缺口；不含操作端識別資料，也不取代即時安全預檢。
- **Reference** · `Operator-observed Tool Runbook` — [ST-LINK SWD 工具操作手冊](development/stlink-swd-tool-operations.md)：整理已驗證的 st-info/st-flash 操作、ST-LINK 排他接線、VTref、Flash Write + 獨立 Readback／SHA256，以及 Reset/NRST 未驗證限制；文件本身不授權實機操作。
- **Reference** · `Operator-observed Tool Runbook` — [KINGST LA2016 工具操作手冊](development/la2016-tool-operations.md)：實測 sigrok AppImage 原生 driver 開啟（不檢查 LA 韌體檔）、被動 SWD 抓波形、成功 Golden Reference、PWM1→CH0 Loopback、PWM OFF 波形驗證；區分歷史成功與當次裝置狀態。
- **Reference** · `internal loopback only` · `HARDWARE NO-GO` — [PSPL-02 / SWD-00 Internal Waveform HIL](development/pspl02-swd00-hil-runbook.md)：三區段 baseline 專用的產物校驗、預檢、受限 MMIO 與原映像復原程序；現場獨立復原及 privileged ownership 尚待確認。
- **Reference** · `HIL-A1.5` · `GitHub-hosted QEMU` · `SWPC NOT RUN` — [ARMv7 Barrier Frozen Artifact QEMU Validation](development/hil-a15-qemu-armv7.md)：以固定 GitHub A1 Run/Artifact、SHA256、ARMv7 QEMU `ctypes` 1,000 次呼叫做 CPU-only 模擬驗證；SWPC 常駐 QEMU 僅建立受控執行方案，實體 Z2 A2 仍 NOT RUN。
- **Reference** · `HIL-A2` · `Path 2 Gate 1 preparation` · `Z2 NOT RUN` — [Cortex-A9 CPU-only Native DMB Contract](development/hil-a2-cpu-only.md)：沿用共用 Dispatcher 與固定 A1 Artifact，定義預設關閉的實機 CPU-only Capability、Work Order、離線驗證及獨立 Evidence；不授權 SWPC／Z2 實機執行。
- **Reference** · `HIL-A1` · `GitHub-hosted cross-build` · `M1 NO-GO` — [ARMv7 Barrier SWPC A1 / Z2 A2](development/armv7-barrier-hil-a.md)：A1 於 GitHub-hosted 以固定 Debian OCI／APT Snapshot 交叉編譯 ARMv7 ELF、驗證 `dmb sy` 並上傳 SHA256 Artifact；原 SWPC A1 實測因工具鏈缺失 FAIL；A2 Z2 執行仍為 NOT RUN。
- **Reference** · `P0` · `Host-only` · `M1 NO-GO` — [Fixed ABI Site 1 Native-Word MMIO Adapter + ARMv7 DMB Candidate](development/p0-fixed-abi-site1-mmio-adapter-host.md)：沿用 LinuxMMIO 的 Site lease、嚴格 ABI 讀寫白名單、要求 Write Barrier 並驗證 COMMIT 順序；原生 ARMv7 Library、實體 Z2／DUT 尚未合格。
- **Reference** · `Host-only` · `PR #1199` — [Native C WordPort Bridge](development/native-c-wordport-gate1-host.md)：在既有 Z2 PS 受保護 Python Owner／Site lease 與本機 UNIX Socket 內，以 SHA-pinned ARMv7 C 處理 Remote Bitbang GPIO/MMIO/DMB；原始 Protocol A/B 為 Host-only 測試，後續經核准實測 DPIDR、v0.1 Flash 與 heartbeat。總 session alarm 600 秒、socket idle 60 秒；[公開執行腳本與操作索引](evidence/native-c-wordport-2026-10-28/README.md)保存可審查來源，原始波形及 Flash 讀回保留於私有工作目錄。
- **Current** · `Path 2` · `Host-only` · `PR #1200` — [Image-agnostic Native C WordPort Programming](development/image-agnostic-wordport-path2.md)：每次 Work Order 動態選擇原始 BIN 與獨立 SHA256，依 exact ICPN Programming Profile／Flash Geometry 計算 Erase；OpenOCD Verify 必要、完整 Readback 選用，使用既有 Z2 PS OpenOCD／PL WordPort；目前只准 STM32F103C8T6 Site 1，尚未部署及執行新的實機驗證。
- **Reference** · `measurement` · `PR #1203` — [SWD Performance Baseline 與階段量測](development/swd-performance-baseline-2026-10-29.md)：紀錄既有 A/B 原始證據、monotonic 階段時間與 Native C／WordPort 計數器對帳；實機新 A/B 量測須符合 Owner/SHA 與 Site 1 安全授權。
- **Reference** · `GitHub-hosted SIM-1／SIM-2` — [Fixed ABI v1 Dual-Site RTL + Protocol-neutral PS↔PL Driver](development/fixed-abi-dual-site-gate1a.md)：Site1／Site2 真實 RTL 模擬引擎、正式 PS SWD Controller 閉環及負向隔離；不代表 Z2／DUT／八 Site 實體驗證。
- **Reference** · `Host-only` · `NO REAL UIO HIL` — [UIO Runtime Backend Phase 2A](development/uio-runtime-backend-host-v1.md)：實作 Fake sysfs／Regular File 專用 UIO mapN、精確物理資源 Pin、Site Lease、Mapping Generation、Failure Injection；**拒絕開啟 `/dev/uioX` Character Device**，M1 仍 NO-GO。
- **Reference** · `Host-only model` · `M1 NO-GO` — [PPU Configuration Owner Phase 2A.1](development/ppu-configuration-owner-phase2a1-host.md)：單一 PPU Admission Gate、同 IC 批次、Quiesce、Synthetic Ownership/Safe-IO 模擬、Lease／Mapping Generation、Fault Injection；**不具實體 FPGA/Kernel 隔離資格**。
- **Reference** · `Host-only interlock` · `M1 NO-GO` — [PPU Configuration Owner Phase 2A.3](development/ppu-configuration-owner-phase2a3-interlock-host.md)：以相同 Boot／Source／Resource／Owner Epoch／Mapping Generation 將 Phase 2A.2 Safety Contract 接入 Ownership、Isolation、Retirement、Verification 與 Mapping Generation 狀態門禁；合成 PASS **不**授權真實 FPGA 載入。
- **Reference** · `Host-only model` · `M1 NO-GO` — [PPU Configuration Safety Contract Phase 2A.2](architecture/ppu-phase2a2-configuration-safety-contract.md)：驗證合成 Ownership／AXI Isolation／Mapping Retirement／Verification 證據之精確 Pin 與 fail-closed 條件；通過不授予 FPGA 載入或實體操作權限。
- **Reference** · `internal loopback only` · `NO Z2 HIL` — [LT02 PS–PL MMIO Loopback ABI](development/mmio-lt02-ps-pl-loopback.md)：新增 FPGA AXI4-Lite Scratchpad／LinuxMMIO 分塊資料比對契約；五 Aperture Build 已由 SWPC 回報 PASS，LT02-05 Z2 HIL 尚未執行，PL UI Endpoint 仍停用。
- **Reference** · `Host-only differential` — [SWD-06 RTL ↔ Python Differential Verification](development/swd06-rtl-python-differential.md)：由 SWD-05 Python Driver 操作 SWD-03 真實 RTL 的 Cocotb AXI4-Lite Bus，僅驗證模擬硬體，Z2 實機尚未執行。

- **Plan** · `Host-only` · `NOT_DEPLOYED` — [SWD NORMAL OpenOCD/ARMv7 Boundary](architecture/swd-normal-openocd-armv7-gate1.md)：獨立 Site NORMAL 交易轉接契約與注入式 32-bit MMIO Window；OpenOCD `plasma_swd` Adapter 的 PS-local 綁定尚未實作（fail-closed），無 DUT 驗收。
- **Plan** · `RTL simulation only` — [PLASMA MPE Two Independent SWD Sites](architecture/plasma-mpe-dual-site-gate1.md)：PYNQ-Z2 Site 1 = PMODA、Site 2 = PMODB，FPGA 硬體自主 SWD 時序、獨立交易與 FIFO 的新 ABI 候選。
- **Reference** · `Host-only` · `d0add58c` — [Independent SWD v5 Image Hardware Contract Audit](development/swd-independent-image-hardware-contract.md)：以 d0add58c HWH 驗證雙 Site Identity 位址（ab79b04e、bd976140 已退役）（`0x43C01000`／`0x43C02000`）與 GP0 連線，及 devmem Owner Admission 契約。
- **Current** · `Engineering` · `Route B` — [ABI-v5 OpenOCD plasma_swd → Blue Pill DPIDR HIL Runbook](development/swd-abi5-openocd-dpidr-hil-runbook.md)：Build／部署／DPIDR 流程、失敗判讀、FPGA 經 HTTP API 交付與載入，以及 §9 Blue Pill Flash（erase／write／verify／read，500 kHz，LA2016 比對 ST-LINK）與 `plasma_swd` adapter 契約。
- **Current** · `Handoff` · `2026-11-04` — [SWD Driver／FPGA 交接](development/handoff/2026-11-04-swd-driver-fpga-track.md)：雙路分工中 PL SWD IP 與 `plasma_swd` adapter 這一路的範圍、目前版本、實測結果（0.5–5 MHz）、C adapter 在 RTL 模擬與 Site 規則 checker（host）、ORUNDETECT／`fault_q` 發現、待辦與兩路介面契約。
- **Current** · `Handoff` · `2026-11-04` — [SWD 整合交接](development/handoff/2026-11-04-swd-integration-track.md)：Runtime／Site Worker／REST `flash_cycle` 這一路的 Z2 狀態、P0（`reset halt`、engine selection、部署 #1286）、後續工作與兩路介面契約。
- **Reference** · `Site 2` · `PR #1304 Draft` · `Host-only` — [Site 2 REST Flash 失敗診斷（2026-11-05）](development/site2-rest-flash-diagnosis-20261105.md)：既有失敗 Job 的 C3 Adapter／OpenOCD／SAFE_OFF 證據缺口與存取限制；不代表真實故障根因已確認或 Z2 實機 Flash PASS。
- **Plan** · `Gate 1` · `PR #1265 Draft` · `Host-only` — [OpenOCD 5088 ARMv7 CI Build Cache Optimization](development/openocd5088-armv7-ci-build-cache.md)：依實際編譯輸入內容建立快取，保留每次驗證、重新封裝及最新 HEAD Evidence；未合併、不部署、不操作實機。

## Deployment

- **Reference** · `Host-only` · `PR #1327 Gate 1` — [Z2 Root Privileged Code 受控升級與 Site 2 驗收準備](deployment/z2-root-code-controlled-upgrade-site2.md)：既有 Root Code Manifest 的離線更新與回復方案，修復 Site 2 唯讀偵測工具；未部署 Z2、未重載 FPGA、未燒錄 DUT。
- **Current** — [PPU Deployment — Start Here](deployment/ppu-deployment-start-here.md)：PPU 只有兩條部署路線——**A. 正式部署**（Console → Bootstrap API（`/v1/uploads` 上傳 → `POST /v1/deployments`），單一 Coordinator；Factory Bootstrap 為前置步驟、`plasmactl z2-ps` 為內部執行器、Bundle v3 為內容格式）與 **B. 工程部署**（SWPC `ppu-deploy` over SSH，僅供開發）——以及部署順序。
- **Current** · `Gate 1` · `Host-only` — [Owner Operation Authorization — user-programmable Bundles](deployment/ppu-owner-operation-authorization.md)：已配對 Console → Manager → PPU 對每個 B2／B3／Runtime 操作簽發綁定 Device、Bundle SHA256、Transaction、Action 的授權；退役逐 Bundle SHA256 白名單（Authority v2）。FPGA 靜態資格、Target、Owner Lock、Journal、Recovery 不變；`execution_permitted=false`。
- **Current** · `Host-only` — [PPU Bootstrap mutual request authentication (LOM-P2A-1)](deployment/ppu-bootstrap-request-authentication.md)：Bootstrap 憑證不再以 Bearer 明文傳送；每個請求以單次 PPU nonce 做 HMAC，PPU 以回應 MAC 證明自身身分。不含加密機密性、不含本機 enrollment（LOM-P2A-2）；Z2 實機 NOT_RUN。
- **Plan** · `NOT authorized` — [LOM-P2A-1 synchronized deployment runbook](deployment/ppu-lom-p2a1-synchronized-deployment-runbook.md)：SWPC Manager／CLI 與 Z2 Bootstrap 同一維護窗口同步部署；版本相容性矩陣、備份、驗收（Pairing、雙向 HMAC、Site 2 Flash/Readback、SAFE_OFF、attempts=1）與雙端協同回復。
- **Plan** · `B1–B5 owner-confirmed; implementation not authorized` — [Local Owner Mode B1–B5 design direction](development/opf-local-owner-mode-b1b5-design-20261109.md)：SD 一次性 Enrollment、每台 PPU 金鑰、單一控制站與實體重新接管、Render profile 隔離、自訂 FPGA NO_GO；重疊 PR #1204／#1215／#1260／#1278 稽核。
- **Plan** · `Frozen spec; not implemented` — [LOM-P2A-0 local enrollment and Recovery-Gated Takeover](development/opf-local-owner-mode-p2a0-enrollment-spec.md)：`plasma.ppu.local-enrollment.v1`：SD 一次性 ticket（boot 時消耗、防重放）、單一控制站與 Controller Generation 原子交接、進行中操作延後接管、SEALED／UNKNOWN 進入 `RECOVERY_ONLY`；test-only 參考模型與 35 個 Host-only 規格測試。
- **Plan** · `Gate 1` · `Host-only` · `PR #1252 Draft` — [One typed Package/Asset Execution Layer — Python, Native C, FPGA](deployment/ppu-common-asset-execution-gate1.md)：共用身分、授權與 dispatch seam；真實 Executor、FPGA Load 接線與 HIL 尚未驗證。
- **Plan** · `Gate 1` · `Host-only` · `PR #1252 Draft` — [Privileged FPGA Source / Root Pin Retirement](deployment/ppu-root-pin-retirement-gate1.md)：新 root-owned 程式完整性驗證與退役相依盤點；Z2／SWD Site Admission／Native C 串接與 Recovery HIL 尚未驗證。
- **Plan** · `Gate 1` · `PR #1262 superseded by #1252` — [Non-root Package Action privilege model](architecture/ppu-rootless-package-action-gate1.md)：owner-operated PPU 的非 root 執行方向、現有 Root Guard 及 Z2 權限稽核缺口；不宣稱已具備 rootless FPGA。
- **Current** · `Host-only` · `PR #1245` — [Generic Bundle v3 B3 — one inert Asset Set staging path](deployment/ppu-bundle-v3-generic-assets-gate1.md)
- **Plan** · `Gate 1` · `Owner decision 2026-11-02` — [Bundle v3 B3 — Install, Activate and Load the FPGA Image in One Transaction](deployment/ppu-bundle-v3-b3-fpga-load-gate1.md)：明確 `fpga_load=true` 的 B3 於同一 Coordinator 交易內安裝、Root `bundle-load`（download＋Identity）並切換 Active Set；待核准，未實作。
- **Current** · `Host-only` · `PR #1246` — [Single Active Asset Set P1 — Console SHA reconciliation & guarded Host-only activation](deployment/ppu-single-active-asset-set-gate1.md)
- **Current** · `Host-only` · `PR #1248/#1249` — [FPGA Asset Handoff P2 — exact Active Image/Profile selection, no hardware load](deployment/ppu-fpga-asset-handoff-gate1.md): removes Smoke-only device allowlist; a staged digest is **not** an Active Set or FPGA load.
- **Current** · `Host-only` · `PR #1217` — [Z2 FPGA six-check admission](deployment/z2-minimal-six-check-admission.md)：FPGA Manager 載入與 MMIO admission 分時檢查；真實 Owner、ABI 與 HIL 尚未驗收。
- **Reference** · `Host-only` · `PR #1209` — [PPU 單一安裝入口收斂](architecture/ppu-unified-deployment-gate1.md)：正式部署路線（Route A）的設計紀錄，不是獨立部署路線；唯一 Bootstrap Deployment API、共用 Coordinator Lock/Journal 目標與 SWPC `ppu-deploy` 三模組過渡驗證；現有 SSH 工程安裝未退役、工程/FPGA Image 的新 API 仍未取得安裝資格，未部署。
- **Current** — [Persistent Integration Host Qualification](architecture/persistent-integration-host-qualification.md)：定義 L4 main-only post-merge qualification、self-hosted/rootful-Docker threat model、fail-closed preflight、runner enrollment boundary，以及為何目前不能把長期 runner 當成 arbitrary-PR execution worker。
- **Current** — [Persistent Integration Runner Enrollment](development/persistent-integration-runner-enrollment.md)：定義 L4 host readiness、GitHub runner enrollment/restriction、首次 qualification、staleness、upgrade、revoke 與 recovery lifecycle；不把 registration token 或 host provisioning 寫入 repository automation。
- **Current** — [Integration Host Deployment Guide](development/swpc-deployment.md)
- **Current** — [Secure Gateway Deployment](development/secure-gateway-deployment.md)
- **Current** — [Fleet Demo Deployment](development/fleet-demo.md)
- **Current** — [Mock Continuous Delivery](development/mock-cd.md)
- **Current** · `engineering SSH route` · `PR #1207` — [通用 PPU 工程模組部署 `ppu-deploy`](development/ppu-deploy-engineering-modules.md)：工程部署路線（Route B），不是產品安裝路徑；Z2 PS WordPort／OpenOCD Python 整合與 SWPC A/B Runner 由同一來源版本協調部署，包含 SHA、互斥、啟用驗證與回滾；目前只有 Host-only 測試，不代表 GitHub PR 已合併或 Z2／SWPC 已部署。
- **Current** — [Deployment Index](deployment/README.md)
- **Current** — [`plasmactl` Deployment Profiles](deployment/plasmactl-deployment-profiles.md)：定義統一 operator CLI、`integration`／`local-control-station`／`swpc-z2like` profile ownership、activation rollback 與 qualification boundary。
- **Current** — [Deployment Port / Profile Matrix](deployment/port-profile-matrix.md)：定義 production、SWPC engineering 與 `z2like-demo` scenario 的 profile-specific port ownership、exposure 與安全邊界。
- **Current** — [Local Control Station Reference Deployment](deployment/local-control-station.md)：定義 Linux user-systemd 的 Console/BFF + Manager 本機參考部署、可設定 PPU Endpoint、loopback-only ingress、immutable release 與 rollback；macOS／Windows 保留相同產品契約但使用平台原生 packaging。
- **Plan** · `partly implemented` — [Product Deployment Foundation](deployment/product-deployment-foundation.md)：定義跨平台 Control Station（macOS／Linux／Windows）、Z2 PPU、SWPC integration host 的產品部署責任邊界，以及 immutable release 與跨平台 read-only readiness audit。
- **Current** — [Product Release Format v1](deployment/product-release-format.md)：定義 product version、release manifest、角色／平台 artifact matrix、SHA-256 integrity、safe verification 與 clean-extraction acceptance。
- **Current** — [Control Station Runtime Packaging](deployment/control-station-runtime-packaging.md)：定義 source-tree-independent Vinext standalone Console/BFF、Manager Python zipapp、runtime manifest 與 Control Station release payload。
- **Current** — [PPU Runtime Packaging](deployment/ppu-runtime-packaging.md)：定義 Z2 PS Phase-1 source-tree-independent PPU Python zipapp、`linux-armv7l` immutable release、PS-only fail-closed configuration、systemd topology與 Managed PS Loopback 驗收邊界。
- **Current** — [PYNQ-Z2 PS Installer and Managed Loopback Acceptance](deployment/z2-ps-installer.md)：定義 verified PPU release → immutable side-by-side install、PYNQ/System-Python ownership isolation、explicit Plasma Python >= 3.11 binding、systemd activation/rollback、local readiness 與 real Managed PS Loopback evidence boundary。
- **Current** · `physical Z2 PS evidence` — [PPU Bootstrap Factory Provisioning and Z2 HIL](deployment/ppu-bootstrap-factory-and-hil.md)：定義獨立 Bootstrap／recovery service、Console-managed Z2 Runtime deployment、durable rollback/recovery contract，以及 real PYNQ-Z2 HIL qualification 邊界。
- **Current** — [SWPC z2like-demo QEMU ARMv7 Backend](deployment/z2like-demo-qemu.md)：固定 SWPC 為唯一 simulation environment、QEMU ARMv7 simulated Z2 為 `z2like-demo` 唯一 PPU backend，並定義 Bootstrap/Control Station 私有路由與非實機 qualification 邊界。
- **Current** — [SWPC Z2-like Configured Mock Programming](deployment/swpc-z2like-configured-mock-programming.md)：將 Engineering Programming 綁定到 canonical `lab/swpc-z2like-01/SITE1..SITE8` 與既有 Plasma Server，明確拒絕 non-mock Site，且不建立舊 32-PPU demo topology；僅屬 software/mock qualification。
- **Reference** — [PPU ARMv7 Runtime Lab](deployment/ppu-armv7-runtime-lab.md)：定義 integration-host QEMU ARMv7 一鍵 runtime/resource 診斷、live／ready／PS Loopback 路徑隔離與非 Z2-HIL 證據邊界。
- **Reference** — [Control Station Runtime Acceptance Evidence](deployment/control-station-runtime-acceptance.md)：定義 macOS／Linux／Windows clean-runtime CI 的證據範圍與不可延伸宣稱的邊界。
- **Current** · `pilot` — [macOS Control Station Installer Pilot](deployment/macos-control-station-installer-pilot.md)：定義 unsigned `.pkg`、per-user `launchd` LaunchAgents、absolute Node/Python runtime binding，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing/notarization readiness。
- **Current** · `pilot` — [Windows Control Station Installer Pilot](deployment/windows-control-station-installer-pilot.md)：定義 unsigned MSI、WinSW-backed Windows SCM services、`Program Files`／`ProgramData` 邊界，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing 或真正 Windows operator-host readiness。
- **Current** — [Web Runtime Hygiene](deployment/web-runtime-hygiene.md)
- **Current** — [Manager BFF Runtime Wiring](deployment/manager-bff-runtime-wiring.md)
- **Current** — [Render Free Public Mock Demo](deployment/render-free-public-demo.md)
- **Current** — [Render Public Smoke Acceptance](deployment/render-public-smoke.md)
- **Current** — [Render Public Browser Acceptance](deployment/render-public-browser.md)

## Development process, Codex and tooling

- **Plan** · `Offline software-pr Gate 1` — [PLASMA Software-only PR Candidate + Mock Publisher Pilot](development/plasma-engineering-software-pr-pilot.md)：Issue #981 的受控 Work Order、離線檔案變更、SHA256 證據與 Mock PR Publisher；GitHub-hosted FAKE Codex 驗證，不代表已運行真實 Codex、自動建立 PR 或啟用 Dispatcher。
- **Reference** · `Dormant Claim Canary` — [PLASMA Engineering Protected Claim One-shot Canary](development/plasma-engineering-claim-canary.md)：Issue #981 GitHub Claim Ruleset 的實際 create/replay/update/delete/readback 驗證程式；僅 Owner 未來單次精確指令才能觸發，現在只執行離線契約測試，**未建立任何真實 Claim、未啟用 Dispatcher**。
- **Reference** — [Codex Software-only Device Permission Read-only Diagnosis](development/plasma-codex-device-permission-diagnostic.md)：針對 Run #39190291831 之硬體節點存取 NO-GO，僅提案裝置節點權限中繼資料、Linux User／Group 與 ACL 唯讀蒐集；PR 合併不會自動啟動 SWPC，實機取證另需明確批准。
- **Reference** · `Development Mode` · `SWPC Monitor；實際工作執行驗收須逐次舉證` — [PLASMA Path 2/3 SSH tmux Monitor](development/plasma-engineering-ssh-tmux-monitor.md)：同一 tmux Window 並排顯示 Path 2 CLI 與 Path 3 Codex；閒置 IDLE、執行時 Run ID／即時進度、結束後 Exit Code。既有監看畫面可顯示兩個 Path，不代表已驗證特定 GitHub Run 的完整即時觀察；須以受授權工作的 Run ID、Log 與 Exit Code 個別確認 PASS／FAIL／NOT_RUN。本條目不設定 Path 3 的 Host-only 前置條件，也不授權部署或硬體操作。
- **Reference** · `RCA closure` · `PR #1128/#1129` — [PLASMA Path 3 Token Optimization RCA Closure](development/plasma-path3-token-optimization-rca-closure-2026-10-23.md)：固定 PR #1128 與兩次 SWPC 9×9 Run ID、Token/時間/81 成功率、Artifact SHA-256 與尚未完成的模型／Effort 因果歸因；Repo-first 工作流 DONE，逐請求 Token Attribution 保留低優先級技術債。
- **Reference** · `local tool` — [Codex Desktop vs Path 3 Token Usage Benchmark](development/codex-benchmark-usage.md)：針對 2026-10-22 9×9 測試，提供僅讀取指定本機 Session JSONL 的 Token 統計工具，區分單次 Turn、累計快照與 Path 3 Codex exec 用量；GitHub-hosted CI 使用合成資料，不代表已讀取 Mac Desktop 真實 Session，也不授權 SWPC、Z2 或 DUT。
- **Current** — [AI-assisted Git Workflow](development/ai-git-development-workflow.md)
- **Current** — [PLASMA GitHub Actions Control Bridge](development/plasma-actions-control-bridge.md)：定義 Issue #814、actor／workflow allowlist、`dispatch`／`cancel`／`rerun` 命令與最小權限安全邊界。
- **Plan** · `Pilot` — [PLASMA Codex SWPC Read-only Bootstrap](development/plasma-codex-pilot.md)：Issue #981 Gate 1 A 的安全派工、獨立 Worker、tmux 監控與驗收邊界；尚非正式部署。
- **Plan** · `Preflight` — [PLASMA Codex SWPC Bootstrap Preflight](development/plasma-codex-swpc-bootstrap-preflight.md)：Issue #981 的現有 SWPC Runner 唯讀前置檢查與真實 Worker 驗證邊界；未執行部署或硬體操作。
- **Plan** · `Host setup` — [PLASMA Codex SWPC Dedicated Worker Provisioning](development/plasma-codex-worker-provisioning.md)：Issue #981 獨立 Linux 帳號、tmux 監控目錄、Runner 註冊與安全驗證的分階段作業程序；文件與程式碼本身不代表 SWPC 已配置。
- **Plan** · `Passive inventory` — [PLASMA Codex Direct HIL Tool Readiness](development/plasma-codex-hil-tool-inventory.md)：重用 Z2 SSH／UART／JTAG、Hub 直接 USB 命令及 KINGST LA Driver／CLI，僅盤點專用 Worker 的 PATH、USB 列舉與裝置權限，不開啟或操作設備；Gate 2 前不觸發實機盤點。
- **Plan** · `Host activation` — [PLASMA Codex Hardware Access Parity](development/plasma-codex-hardware-parity.md)：複製原 Codex 經驗證的 Z2／Hub／KINGST 所需 Linux 裝置權限及已鎖定 sigrok AppImage；僅由 SWPC 受信任管理員在 Gate 2 後啟用，保留原設備權限與兩階段合併審核。
- **Current** — [Codex Cloud Environment](development/codex-cloud-environment.md)
- **Current** — [Local AI Development Guide](development/local-ai-development-guide.md)
- **Current** — [Multi-machine Development Guide](development/multi-machine-development-guide.md)
- **Current** — [VS Code Remote Workspace Standard](development/vscode-remote-workspace.md)
- **Current** — [Mock Runtime Operator Guide](development/mock-runtime-operator-guide.md)
- **Current** — [Operator Acceptance Test Matrix](development/operator-acceptance-test-matrix.md)
- **Current** — [Programming Image Observability Test Plan](development/programming-image-observability-test-plan.md)
- **Reference** — [Mock Runtime Foundation Notes](development/mock-runtime-foundation-notes.md)
- **Plan** · `M0–M4 roadmap` — [PLASMA B/C, SWD Driver and OpenOCD Architecture Simplification Roadmap](development/plasma-m0-m4-architecture-simplification-roadmap-2026-11-03.md)：先完成 Z2 D5/Runtime 安全驗收，再盤點、精簡、實際單 Site 燒錄與八 Site 並行；文件不授權實作或部署。
- **Current** · `debt register` — [Development Debt Register](development/todo.md)

## Operator and acceptance

- **Current** — [Plasma Console Operator Guide](operator/plasma-console-guide.md)：PMode／EMode、Batch Summary、操作與異常復原。
- **Current** — [Runtime Acceptance](testing/runtime-acceptance.md)

## IC catalog, IC support and OpenOCD qualification

STM32F103 OpenOCD qualification: [v7](architecture/openocd-software-qualification-v7.md) is the current umbrella authority for its bounded cohort; v6 is retained as Historical; v1–v5 were removed (see Git history).

- **Current** · `部分實作` — [Target Execution and Interrupt Isolation](architecture/programming-interrupt-isolation-policy.md)：所有 IC 的破壞性 Erase/Program 前預設須驗證目標執行隔離；具中斷的 MCU 必須採用符合 Provider 的中斷遮罩或等效策略，無 CPU／ROM ISP 則須提出適用性或例外證據。現有實機驗證僅及於 STM32F103C8T6 Z2 Site 1，其他 Provider 的 Runtime Gate 仍待實作。
- **Current** — Z2 PS-local OpenOCD + WordPort/RemoteBitbang + paired PL SWD Image for Blue Pill: see root `AGENTS.md`, [PS OpenOCD architecture](architecture/ic-support-openocd-plan-executor.md), [retirement map](development/swd-legacy-path-retirement.md).
- **Plan** · `accepted policy` — [IC Information Catalog Level 0 Evidence Contract](architecture/ic-information-phase1.md)：歷史檔名保留 `phase1`，但正式語意為 Level 0 Exact ICPN identity/evidence；具 programming route 才升 L1，qualification `SUPPORTED` 才升 L2，HIL PASS 才升 L3；L0 僅供 Internal Research，Customer IC Selector 從 L1 開始。
- **Current** — [IC Selector Architecture](architecture/ic-selector.md)
- **Current** — [IC Selector Upstream Evidence / Binding Contract Gate A](architecture/ic-selector-upstream-evidence-consistency-gate-a.md)：區分 OpenOCD 上游 CFG／Driver／DEVID、Production CFG Binding 與 Programming Qualification。
- **Plan** — [KL25 Installed Backend Lock Root v1](architecture/kl25-runtime-backend-lock-root-v1.md)：以既有 IC Support Root 契約載入固定的 KL25 implementation lock，non-editable 安裝與 fail-closed 測試通過才能合併；不新增 KL25 Operation Admission。
- **Current** — [Selected IC Profile v1](architecture/selected-ic-profile-v1.md)：將 exact ICPN 的 Device operating characteristics、Programming requirements、Backend evidence 與 PLASMA compatibility 分層組合；STM32F103C8T6 為第一個 manufacturer-first pilot。
- **Current** · `Design-input contract` — [Programming Hardware and Socket Profile v1](architecture/programming-hardware-socket-profile-v1.md)：以 STM32F103C8T6/LQFP48/SWD 建立 physical pin map、全部供電/接地 contact、NRST/BOOT0 與 package geometry 的 machine-readable Socket design input；明確不宣稱 socket vendor、signal integrity、runtime hardware、HIL 或 execution readiness。
- **Reference** · `source-only L2 proposal` — [STM32F103 Medium-density 非 LQFP 12 顆 exact-ICPN 資格擴展](architecture/stm32f103-medium-nonlqfp-l2-v9.md)：8 顆直接適用性、4 顆 TR 包裝等價；7 顆 VFQFPN36 命名／Geometry 缺口保留 L1，2 顆 R/RTR 特例排除。僅 OpenOCD 0.12.0 原始碼與 ST 原廠證據，不代表實體 HIL 或執行授權。
- **Plan** · `Design-input only` — [STM32F103VBT6 LQFP100 Socket Reuse](architecture/stm32f103vbt6-lqfp100-socket-v1.md)：第四個 ST exact-ICPN 延伸樣板；原廠 DS5319 x8/xB LQFP100 共用 100-pin 接腳、17 個必要接點（含 VREF+/VREF−）、NC 保護；VBT6 獨立綁定 128 KiB／128 頁 L2 幾何，且保留 V8 的 64 KiB 封裝契約，僅 Host-only 驗證，不宣稱 L3／HIL。
- **Plan** · `Design-input only` — [STM32F103V8T6 LQFP100 Socket Profile](architecture/stm32f103v8t6-lqfp100-socket-v1.md)：第三個 ST exact-ICPN 封裝樣板；以 LQFP100 原廠 100-pin map、VREF+/VREF−、5 組 VDD/VSS、NC 接點及 Host-only 負向測試定義獨立設計輸入；不宣稱 Socket/HIL/L3。
- **Plan** · `Design-input only` — [STM32F103RBT6 LQFP64 Socket Reuse](architecture/stm32f103rbt6-lqfp64-socket-v1.md)：在官方 x8/xB 封裝適用性證據下，共用 LQFP64 實體接腳，但將 STM32F103RBT6 的 128 KiB／128 頁 Flash geometry 獨立綁定；不宣稱 HIL、L3 或 execution。
- **Plan** · `Design-input only` — [STM32F103R8T6 LQFP64 Socket Profile](architecture/stm32f103r8t6-lqfp64-socket-v1.md)：第二個 ST exact-ICPN 封裝樣板；64-pin manufacturer-backed pin map、SWD/power/NRST contract 與 Host-only fail-closed tests，尚未宣稱 Socket/HIL/L3。
- **Reference** · `research baseline` — [Manufacturer Enrichment Coverage Framework v1](architecture/manufacturer-enrichment-coverage-v1.md)：定義 M0–M5 manufacturer enrichment coverage、逐 ICPN missing-dimension 投影、explicit exact-ICPN scope composition 與 fail-closed inheritance 規則；不授權 runtime 或 hardware readiness。
- **Current** — [Manufacturer Device Basic Profile v1](architecture/stm32f1-device-basic-profile-v1.md)：目前以 explicit family profiles 覆蓋 STM32F1／STM32F2／STM32C0／STM32G0／STM32G4／STM32U0／STM32U3／STM32L5／STM32H7RS／STM32WBA5X／STM32N6，共 1,622 個 Production exact ICPN；剩餘 3,007 個 ST exact ICPN 已完成 evidence review，但因 Product Selector/eStore 直接證據不足、衝突或無法無損映射至固定 M1 欄位而 fail-closed。IC Information 固定為 10 欄，所有 Basic Profile 與 Programming Profile、Memory Map、HIL 分離。
- **Current** — [STM32H5 Host-only Readback Guard v1](architecture/st-h5-host-readback-guard-v1.md)：190 顆 H5 合成讀值的安全邊界測試；失敗／fallback／不匹配一律阻擋，不代表實機燒錄資格.
- **Current** — [STM32C5 Host-only STLDR Source Guard v1](architecture/st-c5-host-loader-table-v1.md)：139 exact DFP／33 base-only 的離線 Loader 來源與 Tcl array 測試，不能執行燒錄.
- **Current** — [Versioned OpenOCD Provider Registry v1](architecture/openocd-versioned-provider-registry-v1.md)：將 Upstream／ST 來源與 x86／ARMv7 Artifact SHA-256 分離，沒有實機安裝證據不宣稱可燒錄。
- **Current** — [ICPN Backend Candidate Registry v1](architecture/icpn-backend-candidate-registry-v1.md)：H5／C5 合計 362 顆來源鎖定的唯讀候選資訊，與 Production Backend Mapping、燒錄資格分離。
- **Plan** · `proposed contract` — [Device Support and Validation](architecture/device-support-validation.md)
- **Plan** — [Device Support / Hardware Execution / OpenOCD Architecture](architecture/device-support-hardware-openocd.md)：PoC 維持 PYNQ + Python；Production 將 Programmer Backend、stable Plasma HW API、UIO/MMIO/DMA/IRQ 與 PL protocol engine 分層，並避免 OpenOCD per-bit bit-banging。
- **Plan** — [IC Support Reusable Profile Architecture](architecture/ic-support-profile-architecture.md)
- **Current** — [IC Support Coverage Normalization](architecture/ic-support-coverage-normalization.md)：以 derived inventory 將 production exact ICPN 正規化為 Base Device、Programming Profile 與 backend readiness，避免把商業料號數量誤當成燒錄演算法數量。
- **Current** — [IC Support Runtime Resolver Foundation](architecture/ic-support-runtime-resolver.md)：定義 exact ICPN → reusable IC Support profiles 的 runtime-consumable resolver，並維持 Profile resolved 與 backend/runtime implemented 的 fail-closed 邊界。
- **Historical** — [Profile-driven OpenOCD Plan Compiler](architecture/ic-support-openocd-plan-compiler.md)：將 evidence-backed Programming Profile 與 Memory Geometry 編譯成 deterministic OpenOCD dry-run plan；C8／CB geometry 分流，但硬體 execution 維持 fail-closed。
- **Current** — [OpenOCD Software Qualification v7](architecture/openocd-software-qualification-v7.md)：ST Level 0 identity set 維持 4,629 exact ICPN；49 個 exact ICPN 的 Programming Qualification 為 `SUPPORTED`，因此可導出 Level 2 `PROGRAMMABLE`；其餘 ICPN 的 L1 programming-candidate coverage 另由 route projection 決定；Level 3 `PLASMA_VERIFIED` 仍未宣告。
- **Current** — [IC Support Architecture Freeze v1](architecture/ic-support-architecture-freeze-v1.md)：凍結 PR-A／PR-B／PR-C／PR-D 後的 vendor-neutral trust、operation admission、Compiler Registry 與 software/hardware readiness 邊界；不宣稱 HIL 或實體燒錄 readiness。
- **Reference** — [IC Support Local-AI Benchmark Handover](development/ic-support-ai-benchmark-handover.md)：整理 STM32F103C Qwen 實驗的能力邊界、已知 failure classes、multi-model role separation，以及下一輪獨立 Gemma 比較的 blind-control 條件。
- **Current** — [IC Support Semantic Validator v0](development/ic-support-semantic-validator-v0.md)：把 Qwen／Gemma 已觀察到的機械性 failure class 轉成 deterministic semantic invariants、negative regressions 與 CI gate；未具 execution IR 的規則明確維持未實作狀態。
- **Reference** — [STM32F103 Manufacturer-Derived Programmer Codegen Pilot](development/stm32f103-programmer-codegen-pilot.md)：從 manufacturer-derived baseline／Programming Profile／Execution IR 產生 software-only reference programmer，再與 pinned OpenOCD semantic review 做 post-generation differential；不代表 HIL 或實體燒錄 readiness。
- **Reference** — [STM32F103 Real OpenOCD Binary Software Acceptance](development/stm32f103-openocd-real-binary-acceptance.md)：以真正 source-pinned OpenOCD binary、official dummy adapter 與 `target/stm32f1x.cfg` 驗證 C8 64-KiB Flash-driver registration；`noinit` 保證不進入 adapter／target hardware initialization。
- **Reference** — [Microchip Phase 1 SWPC Evidence Vault Handoff](development/microchip-phase1-swpc-evidence-vault-deployment-v1.md)：原廠 Artifact SHA-256 鎖定、SWPC 現場 Preflight、手動 Vault 存入與還原驗收；不宣稱已實際部署或完成異地保存。
- **Plan** — [Device Support Catalog Implementation Plan](development/device-support-implementation-plan.md)
- **Plan** — [OpenOCD Part-number Expansion Plan](development/openocd-part-number-expansion-plan.md)

## CI engineering

- **Reference** · `CI inventory 2026-10-19` — [ICPN Catalog Workflow Rationalization — 2026-10-19](engineering/ci/icpn-workflow-rationalization-2026-10-19.md)：262 筆 Workflow 快照與首批兩個 Microchip 歷史 One-shot 歸檔候選；未完成全部 Actions Run History／Classic Branch Protection 驗證，沒有 Gate 2 合併授權。
- **Reference** · `GitHub-hosted shadow` — [STM32 Historical Governance Shadow Dispatcher](engineering/ci/stm32-governance-shadow-gate1.md)：以原三份 Workflow 的固定 Git Blob、Trigger 聯集、Validator 命令、Runner、Timeout 與負向測試驗證同等性；原 Workflow 不變、不退役，不授權合併或實體硬體操作。

## Evidence records

- **Reference** · `Operator-reported physical HIL` · `PR #1219 admission only` — [SWPC → PYNQ-Z2 Package Admission, 2026-10-30](evidence/ppu-package-admission-2026-10-30/README.md)：實際乙太網路 ZIP Upload／Commit、SHA256、Manifest Admission 與 Receipt；`admitted` 不代表安裝／啟用，TLS、Publisher／Source Trust 和 FPGA／DUT 資格仍未驗收。後續 Factory Bundle 相依檔修復見 PR #1221（已合併）。
- **Reference** · `Path 3` · `Phase A` · `Host-only` — [Blue Pill USB CDC Firmware v0.1 Evidence](evidence/blue-pill-usb-cdc-phase-a-20261023/README.md)：STM32F103C8T6 韌體編譯、ELF／HEX／BIN 靜態核對、Heartbeat／命令 Host 測試與 SHA256；實體 USB、LED、ST-LINK 與 Flash 均為 NOT_RUN，暫用 VID/PID 不是正式 PLASMA USB ID。
- **Reference** · `Path 3` · `Phase A` · `Code Review` — [Blue Pill USB CDC PR #1132 Review Repair Evidence](evidence/blue-pill-usb-cdc-pr1132-review-20261023/README.md)：Documentation CI 修復、連續 SEQ 與可選 Host Port 暫停測試、SWPC 重編譯與 SHA256；實體 USB 斷線與 HIL 仍為 NOT_RUN。
- **Reference** · `Observed` · `LA-only functional PASS` — [2026-10-16 KINGST PWM1 → CH0 Loopback Evidence](evidence/la2016-pwm-loopback/2026-10-16/README.md)：保存 1 kHz／50% 與 2 kHz／25% 實測波形、OFF 對照、SHA256 與離線重算工具；不代表 Z2 或類比電壓驗收。
- **Reference** · `Observed` · `ST-LINK SWD reference` — [2026-10-23 STM32F103 Blue Pill Golden Reference](evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md)：保存三輪 ST-LINK Flash／讀回、六份 LA2016 原始 SWD 波形與離線驗證；CDC 首次 ID 與 SWCLK 時序差異仍未結案，不代表 Z2 燒錄能力。
- **Reference** · `Observed` · `Z2 DPIDR FAIL` — [2026-10-26 Z2 PS OpenOCD + LA2016 Blue Pill Evidence](evidence/bluepill-z2-dpidr-la2016-2026-10-26/README.md)：保存已載入 FPGA 映像的 Identity PASS、兩份原始 LA2016 波形、PS-local Bridge／OpenOCD 失敗收據與測後狀態；第二次擷取的 CH0／SWCLK 全程無邊緣，根因未定。
- **Reference** · `Observed` · `Z2 SWD + page-18 Flash + CDC PASS` — [2026-10-27 實驗步驟與證據](evidence/bluepill-z2-flash-2026-10-27/README.md)、[繁體中文摘要](evidence/bluepill-z2-flash-2026-10-27/SUMMARY.md)、[Step 1–2 原始紀錄](evidence/bluepill-z2-flash-2026-10-27/receipts/step12-result.md)：保存 FPGA BIN/Manifest、PS-local OpenOCD 程式、LA2016 波形、約 3.6 kHz SWCLK 實測、page-18 同內容擦寫讀回及 SWD reset 後 USB CDC heartbeat；未知內容的最後一頁沒有擦除或公開。
- **Reference** · `Observed` · `Z2 Blue Pill v0.1 erase` · `write FAIL → no-erase write PASS` — [2026-10-28 v0.1/v0.2 實驗紀錄](evidence/bluepill-z2-ab-flash-failure-2026-10-28/README.md)：首次 v0.1 擦除後寫入演算法逾時，全片讀回確認前 19 頁全 `0xFF`；之後不擦除直接寫回 v0.1，獨立讀回、同步 LA2016 活動及 reset 後 CDC heartbeat PASS。v0.2 未執行；私有 Flash/波形未公開。
- **Reference** · `Development HIL` · `PASS` — [2026-10-16 Z2 Native MMIO](evidence/mmio-development/2026-10-16.md)：實機 HIL01 Identity／Build ID、HIL02 CONTROL echo 與內部 DPIDR `0x2BA01477`，原始映像及驅動已還原；不包含外部 DUT 或完整 qualification。
- **Reference** · `Hardware Acceptance` · `FULL PASS` — [2026-10-14 PYNQ-Z2 Identity-only PS/PL HIL](evidence/hil-pspl-01/2026-10-14-pynq-z2/README.md)：HIL-PSPL-01 八個 AXI GP0 Identity 讀值及原平台復原；不包含 AXI write、直接 RRESP、FPGA SWD Master 或 IC programming。
- **Reference** · `Offline Preparation` · `HARDWARE NO-GO` — [2026-10-15 PSPL-02 / SWD-00](evidence/hil-pspl-02/2026-10-15-offline/README.md)：離線測試、既有 Vivado 證據與候選／復原產物校驗；新 Z2 HIL 均為 NOT RUN。
- **Reference** — [2026-09-02 SWPC/QEMU ARMv7 Runtime Evidence](evidence/armv7-runtime/2026-09-02-swpc-qemu/README.md)：歸檔實測 JSON 與工程判讀；僅屬 SWPC/QEMU ARMv7 userspace evidence，不代表 PYNQ-Z2 native memory acceptance。

## Historical

- **Historical** · `PR #1241` · `Path 2 B3` — [Bundle v3 B3 Install-only 與受控實機 Smoke](deployment/ppu-bundle-v3-b3-path2.md)：既有 Bootstrap、Coordinator、Installer 接線與 Exact SHA 的 Factory Policy；Host-only PASS 不等於 Z2 實機 PASS，實機 B1/B2/B3 均須獨立證據，無 B4／FPGA／DUT。
- **Historical** · `inventory 2026-10-31` — [Repository-wide documentation governance and cleanup audit](development/plasma-codex-p1-gate1-inventory-2026-10-31.md)：盤點全 Repository 文件權威來源、重複與矛盾規範、歷史文件和引用關係；Codex／Path 3 僅為其中一類，Device Catalog Workflow 暫緩。
- **Historical** · `audit` · `PR #1226` — [Shared Desktop and Path 3 Codex context governance audit](development/plasma-codex-context-governance-gate1-audit.md)：文件權威性、共用上下文與 Token 量測規劃；尚未完成實測節省驗證。
- **Historical** · `retired z2-root-operation Work Order` — [Path 2 受保護 Z2 Root Entry 歷史契約](development/path2-generic-fpga-image-loader.md)：舊 Dispatcher 固定 `download|test|restore` Work Order 已退役，現行 Dispatcher 明確拒絕；獨立兩參數 Protected Root Entry／底層 Transport 與來源、互斥、復原守衛仍保留。#1168 實機 PASS 僅涵蓋當時 Site 1 F1-B，不能推導 Blue Pill／其他 Programmer IP／八 Site 資格。
- **Historical** · `Development Mode` — [Three Shared BLOCKING Decisions](development/development-blocking-policy.md)：Path 2／Path 3 共用授權與來源、Z2 實機安全／復原、真實回執三個核心阻擋邊界；移除重複檢查，但不繞過裝置安全條件。
- **Historical** · `Offline-only Gate 1A` — [Unified Engineering Dispatch v1](architecture/plasma-engineering-dispatch-v1.md)：定義 versioned Work Order、SHA256 owner approval、Capability Policy、離線授權及去重契約；所有既有 Codex Workflows 不修改，僅在未來派工時逐條遷移，**尚未部署或啟用新的 Runtime Dispatcher**。
- **Historical** · `SWPC Codex software-only MVP` · `not yet live` — [Software-only Codex → PR MVP](development/plasma-codex-software-mvp.md)：Issue #981 單次 Owner 指令、真實 Codex Worker、獨立受限 Publisher 與 Gate 2 人工合併；未完成實際 Codex 執行前不得宣稱上線。
- **Historical** — [Device Catalog CI Coverage Map](architecture/device-catalog-ci-coverage-map.md)：記錄 Device Catalog workflow authority、trigger、validator、overlap 與 lifecycle；coverage parity 證明前不授權 workflow retirement。
- **Historical** — [OpenOCD Software Qualification v6](architecture/openocd-software-qualification-v6.md)：legacy Phase 命名文件；以現行術語解讀為 ST Level 0 identity set 維持 4,629 exact ICPN，41 個 exact ICPN 具 `SUPPORTED` qualification、可導出 Level 2 `PROGRAMMABLE`。
- **Historical** — [Historical Multi-Programmer / Multi-Site Naming](architecture/multi-programmer-sites.md)
- **Historical** · `Gate 1 record` — [Codex Native Read-only Preflight](development/plasma-codex-native-preflight.md)：沿用 Issue #981 與既有 Path 2 Dispatcher/Runner，新增固定 main-pinned、無模型 Session 的 Native ELF／SHA-256 唯讀盤點入口；記錄當時未合併、未派工，不代表 PR #1135 已解阻。
- **Historical** · `Host-only` — [F1-B Licensed SWPC Runner Build](development/f1b-licensed-host-build.md)：Path 3 Sandbox 授權失敗的證據、受信任 Runner 修復候選與真實 Build 驗收路徑；候選尚未啟用，Build 未因此宣告 PASS。
- **Historical** · `Path 3 direct tools` — [Path 3 Codex 直接操作 LA2016／Z2 PS](development/plasma-path3-direct-hardware-tools.md)：不透過固定 JSON Host Supervisor，沿用 sigrok CLI、既有 SSH、Z2 PS OpenOCD／WordPort，保留實體互斥、電氣、Manifest 與 Root Guard。原 Issue #981 LA-only workflow 已退役；本次無實機執行。
- **Historical** — [SWD-04 Z2 PS/PL HIL Runbook](development/swd04-z2-hil-runbook.md)：以獨立 Preflight、白名單 AXI MMIO、DPIDR、ABORT 與恢復原 PYNQ 系統的 Host-only 安全契約，實機驗證尚未執行。
- **Historical** · `Host-only` · `Execution Preparation` — [SWD-04 Offline Execution Checklist](development/swd04-offline-execution-checklist.md)：真實 Artifact、BIN 格式、離線工具包、服務隔離與 HIL／Recovery 操作單；缺少復原檔案時禁止載入。
- **Historical** · `Host-only software integration` — [SWD-05 Linux PS SWD Transaction Driver](development/swd05-linux-swd-transaction-driver.md)：基於 SWD-03 AXI ABI 的單 Site Driver、注入式 MMIO、Response ACK、WAIT/FAULT/ABORT、posted AP read 與故障隔離；目前無 Z2 實機資格。
- **Historical** · `superseded by plasma_wordport_program.py` — [Native C WordPort v0.2 SWPC→Z2／Z2 Direct](development/native-wordport-v02-path2.md)：重用 PR #1199 PS-local Native C Bridge，新增固定入口與來源 SHA、v0.2 62,800-byte 一次性 Erase／Program／Verify／Readback，失敗時於同一 OpenOCD 工作階段先讀 DHCSR／FIFO／FLASH 狀態再 Halt 讀 PC／xPSR。GitHub-hosted 僅 Host-only 測試；SWPC／Z2／DUT 執行仍 NOT_RUN，禁止自動重試、Reset 或部署。
- **Historical** · `Host-only software integration` — [Linux MMIO Backend v1](development/linux-mmio-backend-v1.md)：正式 Python 模組使用 native 32-bit mmap 存取、Register Allowlist、Site Lease、Thread Safety 與生命週期保護；已完成 SWD-03 Development HIL（2026-10-16），但未涵蓋 LT02 新 IP。

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
