# ADR-0002: PLASMA Catalog 以 OpenOCD 軟體燒錄支援為顯示門檻，硬體驗證獨立管理

- **Status:** Accepted (product policy; implementation migration outstanding)
- **Date:** 2026-10-14
- **Scope:** Manufacturer Research / Production Identity Catalog / Product IC Selector / OpenOCD software support / PPU-Site-Socket physical validation
- **Owner decision:** 2026-10-14
- **Tracking:** [Issue #849](https://github.com/physicslu/plasma/issues/849)
- **Related:** `docs/architecture/icpn-catalog-admission-policy.json`, `data/device-catalog/production/README.md`, `docs/architecture/ic-selector.md`, `docs/architecture/device-support-validation.md`, `docs/architecture/openocd-versioned-provider-registry-v1.md`

## Context

PLASMA 現階段以 **OpenOCD** 為燒錄軟體 Backend。Manufacturer DFP、Product Search 和 OpenOCD target/flash driver 的覆蓋範圍不同。Microchip Research 已保存 24,051 筆不重複、具來源連結的 *候選* ICPN；這不是經獨立核定的 Microchip 全部可訂購 SKU，更不是 PLASMA 已具備燒錄能力的數量。

Socket、Adapter、PPU 與 Site 等實體硬體測試需購置特定封裝的樣品與治具。若把 Socket HIL PASS 當作 Catalog 顯示條件，便會錯誤排除 OpenOCD 已支援、只是尚未備齊實體測試條件的 IC。反過來，若將所有 DFP 或 OpenOCD CFG 文字命中的 IC 直接列為 Supported，也會虛報實際軟體能力。

目前 Production Identity Catalog 的 admission contract 允許 `no_mapping`；IC Selector 也可以呈現已收錄但尚未映射的 exact ICPN。現行產品顯示路徑因此**尚未符合**本 ADR 的「只顯示軟體支援」新規則。不能把決策方向寫成已完成的 runtime 保證。

## Decision

> **PLASMA 面向一般使用者的 Catalog／IC Selector，僅列出有可追溯證據、由指定 OpenOCD 版本支援燒錄操作的精確原廠 ICPN。是否具有 Socket、Adapter、PPU、Site 實機 HIL 證據是獨立狀態，不是 Catalog 顯示資格。**

具體規則：

1. **Manufacturer Research Catalog** 保存原廠發現的候選 ICPN、DFP 裝置名稱、搜尋失敗、生命週期觀測與證據；不受 OpenOCD 支援與否限制，但不得直接進入公開可選擇的 Catalog。
2. **Production Identity Store / Catalog Admission** 管理精確原廠商業 ICPN 與可驗證來源；資料可因歷史／審核用途保留 `no_mapping`，但內部 identity admission 不等於使用者可見、也不等於燒錄能力。
3. **User-facing PLASMA Catalog View**（包括 `GET /api/devices/search` 的預設商品查詢、`catalog_size`、`total_count`、分頁、IC Selector、PMode／EMode picker、分類數量）**僅包含 OpenOCD software-qualified = SUPPORTED 的 exact ICPN**；各入口的數量與集合必須相同。Research-only、unknown、candidate、unsupported、unmapped 不出現在預設產品選料集合。
4. 軟體支援資格要鎖定 **OpenOCD Provider / 版本或 source commit、Target／Device 對應、Flash Driver、必要的 Flash geometry／bank 假設以及 program、必要 erase、read/verify 等實際宣告的 operation 能力**，保留證據與約束。只有 CFG 檔案名稱、家族字首、確定性 `mapped` 路徑或研究候選，**不足以單獨宣告 OpenOCD = SUPPORTED**。不能在無實體的條件下證成必要晶片特性時，維持 Candidate/Unknown。
5. **硬體驗證獨立維度**：分開保存 IC/package、Socket／Adapter 型號與修訂版、PPU/Site 型號、供電與接腳映射、OpenOCD/PLASMA 軟體版本及測試結果。OpenOCD = SUPPORTED 且 Socket = NOT_TESTED 的 exact ICPN **仍應顯示於 Catalog**；UI 必須明示「尚未實機驗證」，不能標成 Hardware Passed。
6. **執行授權仍分離**：Catalog 顯示不代表目前安裝的 PPU Runtime 已安裝相符的 OpenOCD Binary，也不代表 Socket 適配、電壓、安全、Flash 操作限制均滿足。Job/Batch 必須維持既有 runtime/配置/安全條件的 fail-closed 機制。
7. OpenOCD 是**目前產品 Catalog 顯示門檻**，不是永久禁止未來 Vendor Backend / Plasma-native Backend。變更此政策需另行核准並版本化，不能透過暗中放寬篩選達成。

## Status dimensions

建議的邏輯維度如下（**為政策模型，並非宣稱現行 API 已有同名欄位**）：

| Software state | Qualification | Default product Catalog |
|---|---|---|
| `UNKNOWN` | 尚無足夠證據 | 不顯示 |
| `CANDIDATE` | 部分 OpenOCD Target/Driver 線索，尚未達可證明燒錄條件 | 不顯示 |
| `SUPPORTED` | 版本鎖定、IC 對應、Flash 操作範圍及來源證據達成軟體支援審查 | **顯示** |
| `UNSUPPORTED` | 已審查所指定版本不支援 | 不顯示 |

硬體可以另行記錄 `NOT_TESTED`、`READY`、`PASSED`、`FAILED`，但實際上 **Socket / Adapter / PPU / Site 應是不同的、有版本與 Configuration identity 的證據**，不應用單一扁平狀態掩蓋設備和治具差異。

範例：`openocd_software_support=SUPPORTED` 且 `socket_validation=NOT_TESTED`，IC 可以被搜尋與選取；是否能對某座 Site 執行燒錄，由執行階段另行判定，不應自動允許寫入。

## Migration gap and ownership

- **Accepted now:** 產品政策與證據界線。
- **Not yet implemented:** 新版 public visibility gate、可執行的 OpenOCD software qualification schema、統一 API／UI 集合、遷移後的實際支援數量。
- 現行 `docs/architecture/icpn-catalog-admission-policy.json` 的 `requires_deterministic_backend_route_or_explicit_mapping_state`，是內部 **identity admission** 契約，**不得被誤讀為 Public Catalog 可見規則**。
- 現行 `backend.mapping_status=mapped` 主要表示確定性路由，尚不能概括為已做所有 software qualification；`no_mapping` 更不能當 Supported。Research `backend_candidate` 不可轉為可執行路由。
- 保留既有 Production exact ICPN 資料與研究證據，不透過本 ADR 刪除或大規模匯入 Production rows。
- 後續實作由 [Issue #849](https://github.com/physicslu/plasma/issues/849) 追蹤，須分開審查 source/version qualification、Product API／UI 及 execution gate regression。ST、NXP、Microchip 使用**同一套政策**；不得對不同廠商放寬。

## Validation / acceptance

1. 使用完整 Production manifest 的實際 loaded rows，分別報告 **內部 admitted ICPNs** 與 **軟體已確認 SUPPORTED 的可見 ICPNs**，不手填或繼承歷史 coverage 數。
2. 測試 exact ICPN 有原廠證據但 `no_mapping`、僅 family-matched CFG、只有 candidate source、缺乏可用 Flash driver/operation 證據的資料，皆不出現在預設產品搜尋、picker 和計數。
3. 測試 OpenOCD 已 SUPPORTED，但 Socket／PPU 未測試的 ICPN **仍顯示**，同時標記 Physical Validation 尚未通過。
4. API、UI、分頁、結果總數、Vendor／Family counts 使用同一個軟體支援決策集合；避免 counts 包含隱藏資料。
5. 保持 Job／Batch 的 runtime executable、選定 Site、電氣限制、配置安全與硬體審核獨立 fail-closed；嚴禁由 Catalog presence 推導可執行。
6. Research-only Microchip 24,051 候選與原廠資料庫不受顯示規則刪除或修改。

## Alternatives considered

- **只要原廠候選料號就全部公開**：拒絕；對目前 OpenOCD-only 產品會誤導使用者。
- **只公開 Socket/實機 HIL PASS**：拒絕；把硬體可取得性誤當作 OpenOCD 軟體支援邊界。
- **只要有 OpenOCD CFG 或 mapped 欄位就公開**：拒絕；Target CFG/路由未必代表版本適用且具備可用 Flash 燒錄能力。
- **Research 全部保留，公開只顯示軟體已驗證支援**：**採用**；保留市場發現能力且降低產品支援誤報。

## Decision summary

```text
All manufacturer discovery/evidence → Research (retained)
       ↓ authoritative exact ICPN identity
Production internal identity admission (may include unmapped)
       ↓ pinned OpenOCD software programming qualification
User-facing PLASMA Catalog (SUPPORTED only)
       ├── Socket / Adapter / PPU / Site physical validation (independent)
       └── selected-site runtime and safety execution gate (fail closed)
```
