# Microchip 五組 OpenOCD CFG / 2,563 Exact ICPN — ST-style Phase 1 Information v1

## 合約與現況

對齊 [ST Phase 1 field ledger](adr0002_st_phase1_information_v1.py) 與
[ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
的每欄獨立證據驗收，而非沿用 ST 先前全有或全無的 M1 方式。

**固定 Research 工作子集合：**原始 Microchip MCP 23,276 筆 S1 `IDENTIFIED` 中，
與鎖定版本 OpenOCD 0.12.0 的 Target CFG 反向交叉引用命中的 **2,563 筆**。
這只是 Phase 1 IC Information 的**有界研究子集合**，不是 2,563 筆已通過
OpenOCD Flash programming 的聲明。

| CFG | ICPN |
|---|---:|
| `tcl/target/pic32mx.cfg` | 1,241 |
| `tcl/target/at91samdXX.cfg` | 667 |
| `tcl/target/atsame5x.cfg` | 354 |
| `tcl/target/atsamv.cfg` | 175 |
| `tcl/target/atsaml1x.cfg` | 126 |
| **合計（exact ICPN 去重）** | **2,563** |

由 `microchip_phase1_cfg2563_st_field_ledger_v1.py` 在同一 GitHub Actions job，
從**原始檔重播**的全體 MCP/DFP 來源、官方 MicrochipDirect HTML Chart、既有
P0 2,437 / P1 126 的 Phase 1 欄位 Ledger，以及 S1 原廠商業身分驗收清單，
產生完整 **2,563-record** 的報表 Artifact。

這個新 Ledger **不會新增原廠事實**；它把已經擁有的可追溯欄位，以 ST 相同的
`value/state/source_scope/source_authority/source_locator/source_sha256` 概念，
整合成統一 IC Information 資料形狀。Microchip 原始欄位 `vdd`
在統一輸出中明確轉為 `working_vdd`，**不等於 `io_supply` 或 `vdda`**。
額外保留 `core_architecture` / `core_model` 為選用欄位。

## 原廠資料與目前可驗證涵蓋率

| 各個獨立欄位 | VERIFIED | PARTIAL | UNKNOWN | CONFLICT |
|---|---:|---:|---:|---:|
| manufacturer / icpn / base_device（各欄） | 2,563 | 0 | 0 | 0 |
| package / pin_count / flash / ram（各欄） | 0 | 2,496 | 67 | 0 |
| working_vdd / temperature / core_model（各欄） | 0 | 2,496 | 67 | 0 |
| io_supply / vdda / core_architecture（各欄） | 0 | 0 | 2,563 | 0 |

- **2,496 PARTIAL**：原廠參數 Chart 已有 Base Device/Family 層級的七項
  規格資料；其原始 HTML SHA、TR 行序、欄名、原始值與單位均由既有
  Evidence Ledger 保存。**不是**特定 `-I/xxx` 等精確訂購後綴的規格驗證。
- **67 UNKNOWN**：目前觀察的 32-bit 官方 Chart 範圍未提供已批准
  Base Device 對應。不能由料號字尾或 CFG 猜測封裝、腳位、電壓、記憶體。
- **全 2,563 I/O Supply／VDDA** 保持 UNKNOWN；不能用 VDD 複製填入。
- **S1 = 2,563（全部已位於整體 S1 = 23,276 之內）**；
  **S1_complete = 0**。後續從 datasheet 實際提升 VERIFIED 時，須另以
  原廠文件修訂、特定表格/頁碼與 exact-family 適用證據驗收，不得以數量目標
  驅動無證據升級。

## 逐筆資料形狀

每筆具有完整 ICPN、Microchip Original MCP Base Device、研究用 CFG 路徑、
研究排序 P0/P1、原始 MCP 身分 SHA 引用、原始來源觀察時間、十三個 ST 式
IC Information 欄位及獨立證據狀態。額外的 Family 欄目前只是
`family_research_hint`，不能被當成正式原廠型號／封裝適用證據。

凍結基準不是依 2,563 這個數字臆測：CI 對
`(exact ICPN, manufacturer Base Device, Target CFG)` 排序後做 Canonical SHA-256，
輸出 `cfg_identity_freeze_sha256`；並鎖定五組 CFG 的逐組人數與跨組唯一性。
**當得到 CI 第一次正式 Digest 後，需再將 Digest 固定寫回驗證 Gate**。
此文件不預先捏造尚未量測的 SHA。

## Product/Selector 分離

**此 PR 僅建立可供未來 IC Information detail 使用的來源資料契約。**
目前標準 IC Selector 使用 Production Identity Manifest，尚未接入這個
Research-only Artifact，所以**合併此 PR 仍不會直接讓 Microchip 2,563 筆
出現在 IC Selector**。

後續 UI/API 工作應使用分離的 **Phase 1 Research 唯讀查詢**，顯示
`IDENTIFIED`、`INFORMATION_INCOMPLETE`、`UNKNOWN` software qualification；
不可僅因有 CFG 就將其混入面向使用者的可燒錄清單、
`openocd_software_support=SUPPORTED`、Job/Batch、Programming Profile
或 Phase 3 HIL。本 PR 沒有對 Production/Selector/Job 進行變更。

## 驗證

在 Microchip CFG-first GitHub Actions workflow 中：
原始 313 source-attested MCP batches + 原廠 DFP index + 原廠 32-bit Chart
全部重播；五個 CFG Exact ICPN 人數、2,563 唯一性、各欄覆蓋率、官方
SHA/來源定位、S1 Identity、S1_complete、研究資格與公開可見性隔離
均 fail-closed。先跑負向 unittest，再執行產出與重播比對。
