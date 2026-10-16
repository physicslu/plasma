# PLASMA — Runtime FPGA Architecture v1.0

> **狀態：Plan / Proposed Roadmap（非 Current Implementation，也不是 HIL PASS）**
>
> **記錄日期：2026-10-16**
>
> **工作範圍：** FPGA Hardware ABI、Linux Runtime Driver、FPGA Image Lifecycle／Dynamic Switching、Dual-Site HIL 與後續 8-Site 可擴展性。
>
> **授權邊界：** 此文件型 Draft PR **只記錄規劃**。不授權修改 Driver／RTL、部署服務、載入 Bitstream、存取實機 MMIO、操作 DUT、修改 main 或合併任何 PR。新實作需依 AGENTS.md §11 的 Gate 1 批准計畫；Merge 需獨立 Gate 2 批准。

## 1. 已確認的 PPU 產品前提

1. **單一 PPU FPGA Configuration：** 一台 PPU 在任意時刻使用一份有效的 FPGA Bitstream，不論配置 2、4 或 8 個 Site；Bitstream 不隸屬單一 Site。
2. **同批次同一種 Target IC：** 一台 PPU 的同一燒錄批次中，全部 Site 燒錄同一個 exact Target IC 型號，共用 PPU-Level Programming Profile／Algorithm。允許個別 Site 有不同序號、MAC、校正值等 per-DUT payload。
3. **Site 執行獨立：** Site 有個別交易狀態、逾時、結果、錯誤隔離、Buffer，以及獨立的 DUT Power／Reset 控制。相同 IC 不代表必須同步進行。
4. **使用者切換 IC／Interface 不重啟 PPU：** 更換 Target IC 或 SWD／JTAG／SPI／I²C 等 Interface，必須在 Linux、Ethernet、Plasma Gateway 持續運行的條件下完成。允許前批次結束後短暫 SWITCHING／NOT_READY，但不是 Linux reboot。更換 IC 型號不代表一定需要更換 Bitstream。
5. **只有一個 FPGA Configuration Owner：** 所有 Bitstream Reload 由 PPU-Level Hardware Manager／Supervisor 協調。任何 Site Busy、殘留 MMIO 使用者或無法驗證的硬體所有權，都應拒絕切換。
6. **正常燒錄禁止 Reload：** Site 進行 programming／verify／erase 等硬體交易期間不得重新配置 PL。

與既有文件的關係：

- [Facility／PPU／Site Model](ppu-facility-sites.md)：Site ID 仍從 1 開始，Site 與 Socket 不相同。
- [PPU Execution Ownership](ppu-execution-ownership.md)：單一 PPU「邏輯 Job Owner」是 Control-Plane Admission；本文件的單一「FPGA Configuration Owner」是硬體資源責任，**不得把兩者視為同一把鎖**。
- [Device Support / Hardware Execution / OpenOCD](device-support-hardware-openocd.md)：Programming Semantics、OpenOCD／Vendor Backend 與 Hardware／Recovery Plane 維持分層；本計畫不移轉到 OpenOCD 管理 FPGA Reload 或 DUT 電源的權限。

## 2. 硬體與驅動的設計方向（待 Phase 1 證據確認）

### 2.1 一般換 IC 優先不重載 FPGA

依序選擇：

1. **Software Reconfiguration**：同協定更換 exact IC Profile、Flash Algorithm、Transport 參數／時序設定，沿用相同 FPGA。
2. **Universal／Multi-Protocol Image**：已實作的協定 Engine 可在軟體命令下選擇；不重新載入 FPGA。
3. **Runtime Dynamic Bitstream Switching**：只有當當前映像不具備必要硬體 Capability 時，才在全部 Site Quiesced 後以 Linux FPGA Framework 載入另一個 image；**Linux 不重啟**。

是否能把常見協定都放進同一份 Zynq-7010 Bitstream，必須用實際 LUT／FF／BRAM／Timing 資料決定。禁止事先宣稱單一影像能支援全部協定。

### 2.2 Driver／MMIO 架構選項

比較、驗證再決策，不提前把 UIO 視為唯一方案：

- **DevMemBackend**：保留受控 PYNQ-Z2 開發及比較用途；不可將 advisory flock 說成 Kernel 強制授權。
- **UIOBackend**（優先 PoC 候選）：解析 sysfs 的 uio maps／offset，對應 mmap 與 Device Tree；檢驗單一 PPU UIO 或 per-Site UIO 的實際可行性。
- **Custom Kernel Driver**：如果 UIO 無法支援所需的 DMA／IRQ／重新配置所有權／強制隔離／存取策略，再評估。

共同上層應使用穩定、經版本化的 Plasma Hardware API／32-bit MMIO primitive；上層 Site Driver、SWD／SPI Engine 不應直接依賴 `/dev/mem` 路徑或絕對 AXI 位址。建立 Site Lease 及單一配置 Owner。**UIO 仍容許多 Process mmap，並不自動提供 per-Site 排他或阻止未合作的程式。**

**待實證問題：** 現有 PYNQ-Z2 Fabric UIO 的 `0x40000000–0x4000FFFF` Driver binding、sysfs maps、Device Tree、Kernel 使用者及解除綁定條件；UIO 資源宣告本身不必然代表 Kernel 持續對暫存器發出交易。需由真實證據分辨 Resource Owner 與 Active Access。

### 2.3 固定 Hardware ABI v1（待定義、不得直接沿用 MS01 當產品 ABI）

不同 Image 的 Driver 可見介面應盡量一致，至少審核：

- Identity Magic、Hardware ABI Major／Minor、Build ID、Image ID、Capability Bitmap。
- PPU Global Status／Control、Site Count／Site ID、Site Register、Error Status、版本相容性政策。
- AXI Aperture Map、Byte Order、Access Width／Alignment、Reserved Registers、不可觸碰位址、同步及狀態轉移。
- Site-Level Control 與 Board-Management Power／Reset／Mux 安全控制的分界。
- 不相容 ABI、新的 Device Tree Resources 或新增 IP 需明確 Fail Closed，不能只比對檔名或 FPGA Manager `operating` 狀態。
- Identity／ABI／Capability 的實際 Readback 必須由匹配的 Bitstream 證明。

固定 ABI 降低 Driver 重配置成本，但**不保證** FPGA Reload 時 MMIO 安全；仍需 Quiesce、Owner Check、必要硬體隔離及重新驗證。

## 3. FPGA Image Lifecycle 與安全條件

**目標：** Linux、Boot ID、Ethernet、SSH、Plasma Gateway 在正常介面切換期間保持運作；Gateway 可以回覆 `SWITCHING`／`NOT_READY`／`FAULT`，但切換時不得接受新的燒錄硬體交易。

概念狀態機：

~~~text
READY -> QUIESCING -> VERIFY_OWNERSHIP -> ISOLATING
      -> LOADING -> VERIFYING -> READY
                                |
                              failure -> RECOVERING
                                         |       |
                                      verified  failed
                                         |       |
                                        READY   FAULT
~~~

- FPGA Manager 負責 Bitstream 載入；Supervisor 負責 Life-cycle Admission、Mapping／Driver Owner 交接、驗證、復原與證據。
- 所有 Site 交易終止且相關 kernel driver、UIO、fd、殘留 mmap、其他 PL Consumer／DMA Owner 已符合受控退出條件後，才允許 Reload。
- 應確認 Zynq-7000 目前 Kernel、Device Tree 與設計是否真正提供 PS↔PL 隔離／FPGA Bridge；不可假設 unbind UIO 等同 AXI Hardware Isolation。
- FPGA Load 前確認 BIT／HWH／Manifest／BIN exact digest、Board Part／FPGA Part、Recovery image 與 rollback path。載入後需確認 Current-Boot Receipt、Image Identity／ABI／Capability、Clock、驅動與 Linux 服務狀態。
- **不保證完全自動恢復 AXI Stall／Kernel Hang**：Python timeout、finally、fd close 都不能單獨確保 bus transaction 結束；需有 NO-GO 與板外恢復策略。
- 正式實體 Socket 在 FPGA Reload 期間要有不依賴可重新配置 PL 的 DUT safe-state 機制（Output Enable／Power／Reset／隔離；實際電氣設計待驗證）。
- 如 Profile 已能由目前 Universal Image 支援，切換 IC 不應無故動態重載 FPGA。

## 4. 工作 Phase 與 Codex HIL 驗收

Phase 為**工作分段，不新增 Approval Gate**。每個 Phase 的 Gate 1 授權範圍、實機風險與實作 PR 由 Owner 另行明確批准；此 Roadmap PR 不是任何實機操作授權。

| Phase | 工程成果／Codex 工作 | 必須保留的驗收證據 | 狀態 |
| --- | --- | --- | --- |
| **0：既有 MS01 安全收尾** | PR #972 的 B1 Fabric UIO Ownership、B2 六 Aperture／殘留 mmap Guard、B3 六 Aperture Supervisor；完成 Host Fault Injection／CI | 原始 Host Vivado Artifact Hash、B1/B2/B3 Trace、PASS／BLOCKED；不可把 Host Tests 當 Real Z2 HIL | **進行中（另 PR）** |
| **1：Driver & Hardware ABI Architecture** | 現況盤點、比較 UIO／devmem／Kernel Driver、UIO Device Tree、Site Leasing、固定 ABI v1 與 Image Compatibility；提出 Architecture Decision | Driver 選型理由、實際 Z2 Kernel／UIO Inventory、ABI／Address Map、相容性與破壞性變更策略；Architecture Review | **Plan** |
| **2：UIO Runtime Backend** | 與既有 DevMem Backend 同 API、UIO sysfs Map 解碼、合法 u32 read/write、所有權與清理、Fault Injection；先 Host 後已授權 Z2 HIL | Host Regression、UIO-01 mapping、UIO-02 identity、UIO-03 合法 access、UIO-04 Site 1/2 isolation、UIO-05 cleanup、UIO-06 lease、UIO-07 reload exclusion；無無效實機 AXI 探測 | **Plan** |
| **3：Generic FPGA Supervisor** | 將 Phase 0 Development Supervisor 演進為通用 Image Registry／ABI admission／Reload／Recovery，與 Runtime Backend 整合 | SUP-01..10：正常狀態轉移、busy／mmap／Driver conflict、hash fail、load fail、recovery fail、Process／Supervisor crash、預設 inert；全部 Host-only | **Plan** |
| **4：Runtime Dynamic Switching HIL** | 準備兩份**真正不同**、相同 Driver-visible ABI 的 Image A/B；受控 Z2 A→B→A，不重新開機，使用實機 Driver／FPGA Manager | SW-01..12：Load／Back、Driver／ABI／Capability、Ownership、UIO Mapping、SSH／Ethernet／Gateway、Rollback、Boot ID 相同、有限重複切換；外部 AXI fault 不強制在 Z2 注入 | **Plan** |
| **5：Dual-Site Functional & Performance** | Real ARMv7 Site 1/2 Function、Thread、Process-IPC、資料隔離、CPU／RAM／Time／Throughput／Latency；復原與回報 | 真正 Z2 HIL，2-Site Site 狀態／Counter／CRC、P50/P95/P99、CPU、RSS/PSS、Perf CSV／JSON／SVG、base image verified restore。Process-IPC **≠ Process-Direct MMIO** | **Plan** |
| **6：8-Site & Zynq-7010 Capacity** | 用 Phase 1 ABI 將 RTL／Firmware 擴展至 8 Site，評估 SWD／JTAG／SPI／I²C／ICSP 需求、Engine 複用、Resource、時序、每 Site 電氣安全 | Vivado 7010 LUT／FF／BRAM／Timing、Host RTL Contract、2→4→8 Scaling、真實硬體具備時 HIL；無實機不可宣稱 8-Site PASS | **Plan** |

### 4.1 Phase 2 Real Z2 HIL Gate（依批准範圍執行）

- UIO-01：辨識正確且與 Artifact ABI 相符的 UIO 設備與 Map。
- UIO-02：在已驗證映像下正確讀取 Identity／Build ID。
- UIO-03：僅執行預先許可、已知合法且對齊的 32-bit 交易；不以 Z2 probe invalid AXI offset。
- UIO-04：Site 1/2 資料、Count／Status 獨立；實機結果不推論 8 Site。
- UIO-05／06：Close／Unmap／Site Lease／Other Process conflict 受控。
- UIO-07：切換準備期禁止新交易並拒絕不完整所有權。

### 4.2 Phase 3 Host-only Fault Injection

- SUP-01：正常狀態轉移。
- SUP-02：Site Busy 拒絕切換。
- SUP-03：mmap 尚存拒絕。
- SUP-04：Driver Ownership 衝突拒絕。
- SUP-05：Candidate／Recovery SHA 不符拒絕。
- SUP-06：Load failure。
- SUP-07：Recovery／UIO rebind failure。
- SUP-08：Worker／Benchmark Process crash。
- SUP-09：Supervisor crash／中斷的持久化狀態與補救規則。
- SUP-10：預設 Dry-run／No hardware side effects；例外不可假定完成物理恢復。

### 4.3 Phase 4 真正的 Switching HIL

- SW-01／02：Image A→B→A，兩種 Image 必須不同且共同 ABI 經確認。
- SW-03／04／05：Driver-compatible ABI、Image Identity 與不同 Capability 正確。
- SW-06／07：No active MMIO owners；新映像的 UIO/Map 正確。
- SW-08／09／11：Boot ID 不變、SSH/Ethernet 正常、Gateway 狀態可查（切換期間不執行硬體燒錄）。
- SW-10：故障時受控 Rollback，失敗時真實標示 FAULT／需要人工介入；不能虛構成功。
- SW-12：逐步增加 A／B 次數、留存 Linux Kernel／FPGA Manager Evidence；切換成功仍不等於 DUT programming qualification。

## 5. 並行工作與硬體工作阻擋規則

**不要全面凍結 PLASMA。先凍結尚未定案的硬體介面，讓無硬體依賴的工作持續前進。**

| 工作類別 | 是否可和 Phase 1～4 並行 | 條件／依賴 |
| --- | --- | --- |
| ST／NXP／Microchip exact ICPN discovery、L0／L1／L2 Software Qualification | **可以** | 僅資料／軟體證據，不主張 Physical HIL／L3 |
| OpenOCD target／Flash Algo 的 Software-only tests | **可以** | 不預先固定未核准的 PL Adapter 介面 |
| Console、Mock、API 與無實體 PL 依賴的開發 | **可以** | 保留既有 contracts，不冒用新的 FPGA Capability |
| 現有 PR #972 B1～B3 Host 安全收尾 | **繼續** | 獨立 Gate／PR，不因新 Roadmap 打斷 |
| 正式 8-Site RTL 大規模實作、產品級 Register Map Freeze | **阻擋至 Phase 1 Architecture Freeze** | 必須依照共同硬體 ABI／Driver 決策 |
| 新的實體 PL Programming Adapter、Site Power／Reset 介面整合 | **先限於模擬／契約研究** | 實體整合必須依據核准 ABI、Driver、安全控制契約 |
| 實際 Runtime Bitstream Switching／UIO HIL | **需 Phase 2／3 的 Safety Readiness** | 仍受各工作 Gate 1 的實機操作授權約束 |
| 八通道正式實機效能與 IC Programming HIL | **等相關硬體能力與必要安全 HIL** | 不得以 QEMU、Host CI 或 Dual-Site 結果冒充 8-Site PASS |

### 5.1 三個工程里程碑（非第三批准 Gate）

1. **M1 — Architecture Freeze：** Driver 選型、固定 ABI v1、Owner／Lease、切換協定與驅動生命週期有經審核的決策；**解除符合 ABI 的 RTL／Backend 開發阻擋**，不表示實機驗收完成。
2. **M2 — Dynamic Switching Real Z2 HIL PASS：** Linux 不重啟、不同 A／B Image 可安全切換、Driver／Gateway 可用與 Recovery 證據。解除多協定實機整合的主要風險；不表示所有協定已完成。
3. **M3 — Dual-Site Performance HIL PASS：** 正式 Runtime Backend 的兩 Site 功能、隔離與效能有真實 ARMv7 證據；再投入 8-Site 大規模資源與性能最佳化。

後續執行允許 Phase 2／3 交錯開發，但 **不能因進度壓力跳過被依賴的安全檢查**。先獲得最小可驗證垂直切片，再逐步擴大。

## 6. 既有事實、未知與證據邊界

- **PR #972**：MMIO-MS-01 Dual-Site six-aperture Candidate，SWPC Host-only Vivado Implementation、BIT／HWH／Manifest 與 Candidate BIN 已有證據；B1／B2／B3 Remediation 在獨立 PR 收尾。不要在此 Roadmap 宣稱已完成實機 dual-site HIL 或 merge。
- **HIL-A**：已回報 BLOCKED／HIL-B NO-GO。Fabric UIO 擁有 `0x40000000–0x4000FFFF`，Site 2 fd-close／retained /dev/mem mmap Guard 有 Host 可重現漏檢；尚缺六 Aperture Supervisor 的實機 Load／Recovery 證據。
- **過去五 Aperture HIL**：之前的 Base Image Restore PASS 不可視為新六 Aperture Supervisor PASS。
- **待證明：** Kernel UIO 是否適用、PS↔PL Hardware Bridge、fixed ABI 共用成本、Zynq-7010 邏輯資源、FPGA Reload 期間的外部 DUT 硬體安全狀態。
- **沒有實體 DUT 的 HIL** 不等於 SWD/JTAG/SPI/ICSP IC Programming 能力，也不能等同 ICPN L3 `PLASMA_VERIFIED`。
- 本文件不變更 ADR-0002 的 Catalog Level 任何語意。

## 7. Codex / Owner 責任與 Gate

- **Owner／架構審核（這裡）：** 確認產品前提、Driver 與 ABI Decision、各 Phase GO／NO-GO 與可接受的 HIL 證據，審核必要 Gate 1 與 Gate 2。
- **SWPC Codex：** 在已批准的具體 Plan 內實作 Driver／RTL／Supervisor、Host Test、Vivado、Z2 HIL、PR／CI、原始 Logs／Hashes／Recovery 結果；如出現 AXI Stall／存取權衝突，真實標記 BLOCKED／NO-GO。
- **AGENTS.md §11 只有兩個批准 Gate：** Gate 1 = Plan Approval，Gate 2 = Merge Approval。Phase、HIL-A/B、M1/M2/M3 都是執行／技術驗收階段，**不是新的 Approval Gate**。
- 此 Roadmap Draft PR 的工作完成，**不代表**任何 Phase 1～6 已獲授權。待現有 Codex 將 PR #972 安全收尾後，再開 Phase 1 的範圍與 Gate 1 工作計畫。

## 8. 開始 Phase 1 前的檢查清單

- [ ] Review PR #972 B1／B2／B3 收尾與仍未完成的實機風險。
- [ ] 梳理已有 [Hardware Execution / OpenOCD 設計](device-support-hardware-openocd.md) 及 SWPC 的 Kernel／Device Tree／UIO 事實，避免重複建立 Supervisor。
- [ ] 定義 Hardware ABI v1 的相容性規則、地址、Capability、Identity、Site 狀態。
- [ ] 比較 single-UIO vs per-Site UIO vs Custom Driver（資源／隔離／Lifecycle）。
- [ ] 確定 Real Z2 的 HIL Driver／Switching 與 Original Image Recovery 安全契約。
- [ ] 提交 Phase 1 明確範圍與 Gate 1 Approval，**此文件 PR 不取代批准**。
