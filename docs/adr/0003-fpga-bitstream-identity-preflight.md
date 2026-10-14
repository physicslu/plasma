# ADR-0003: FPGA Bitstream Identity 與 Programming Preflight 分離原則

- **Status:** Accepted（設計決策；實作尚未完成）
- **Date:** 2026-10-14
- **Scope:** PLASMA PPU、Zynq PL、Programming Profile / Hardware Preparation
- **Technical standard:** [FPGA Bitstream Identity / Compatibility / Lifecycle v1](../architecture/fpga-bitstream-identity-lifecycle-v1.md)

## Context

PLASMA 的 IC 燒錄任務由 Programming Profile 宣告所需的硬體能力；PL 可能需依任務載入相容 Bitstream。Bitstream 更新不應被當成 Console 的一般平台維護行為，也不能因切換料號而無條件重配置 FPGA。Zynq PL 的完整重配置可能同時影響多個 Site，必須遵守 PPU-wide 排他與安全條件。

現行 Z2 `z2-ps` Runtime/Bootstrap 僅具 PS-only 部署能力；`fpga_update=false`，尚未具備完整 FPGA Configuration Manager、PL Identity register 或實體 SWD HIL。

## Decision

1. **獨立版本管理。** 每個正式 PL Bitstream 有獨立 Semantic Version、Hardware ABI Version、Build ID、SHA-256、Target Board / Revision 與明確 Capabilities；不與 Plasma Product Version 混用。
2. **可讀的實體識別。** 正式 Bitstream 必須實作 PS 可讀的 PL Identity Register Block，至少包含 Magic、Bitstream Version、ABI Version、Capabilities 及 Build ID；Manifest 必須包含完整 Git SHA、完整 Bitstream SHA-256 與建置來源。
3. **按能力決策而非按料號映射。** 選定 exact ICPN → Programming Profile → 所需 PL Capabilities / ABI → PPU 讀取實際 PL Identity → 相容則沿用，不相容才評估重新載入。不要為每一顆 IC 建立獨立 Bitstream 作為預設模式。
4. **PPU 掌握啟用權。** Bitstream 可隨已驗證的部署資產預先配送，但配送不等於啟用；是否載入、何時載入由 PPU Programming Preparation / FPGA Configuration Manager 管理，不由 Browser 直接寫 FPGA。
5. **完整重配置採 PPU-wide 排他。** 全部 Site 必須閒置、沒有活動中的 Programming Job，且完成安全 I/O/target-power preflight，才允許重配置。不可因新 Job 打斷其他 Site。
6. **Fail closed。** 無有效 Manifest、讀不出 PL 身分、ABI 不相容、Capabilities 不足、Target Board 錯誤、完整性不符或重新載入後回讀不一致，均拒絕硬體 Programming。
7. **PS 維護與 PL 運行分責。** Console 的 Platform Runtime Deployment 維持管理 PS Python / PPU / OpenOCD；FPGA Bitstream 的選擇與啟用是 Job Preflight 流程。既有 Bootstrap `fpga_update=false` 不因本 ADR 而改變。

## Rationale

Bitstream 版本代表特定硬體實作，Hardware ABI 代表 PS↔PL 契約；兩者獨立有助於避免不必要重配置。PL 自身回報 Identity 可避免只相信「上次載入」的快取狀態。完整重配置是整台 PPU 的破壞性共享資源操作，不能按單一 Site 局部成功來推定安全。

## Consequences / Migration

- 第一個正式 Z2 EMIO GPIO PoC 必須導入可讀的 PL Identity 和 Manifest；既有 `btled` 是教學/開發示例，並未具備此契約。
- 首次實作需定義 AXI-Lite/PS 讀取路徑、具體 address map、Vivado Build、Version/Capability guard、Site 互斥、硬體電氣安全與 HIL 驗收。
- 此決策**不代表**目前已可透過 Console 載入 Bitstream、不代表 FPGA SWD Master 已完成，也不代表任何 IC、Socket 或多 Site 實體燒錄已合格。
- Partial Reconfiguration、簽章驗證與跨板型發行策略均另行設計，不可默認已支援。
