# Microchip SAM L10/L11 — Phase 1 首批 122 Exact ICPN Selector Admission

## 目的與邊界

這是依照現行 ST／NXP 既有的 **Production Identity Admission → IC Selector
查詢**流程，新增 Microchip 第一批原廠料號查詢；**不是** Phase 2
OpenOCD `SUPPORTED`、Programming Profile、PPU／Socket／Site HIL、量產燒錄
或主機 Runtime 部署。

本工程拆成相依的兩個 PR：

- [#921](https://github.com/physicslu/plasma/pull/921)：原始 Microchip MCP
  commercial `partNumber` + 原廠 DS60001513G 印刷 p.14／p.16
  訂購碼適用範圍證據，六個逐欄位 Exact SKU `VERIFIED`；4 筆特殊
  VAO 仍待查，保持 `PARTIAL`。需先通過獨立審核。
- [#924](https://github.com/physicslu/plasma/pull/924)：將 **122 筆**
  正式來源證明的 Exact ICPN 以**第一批實作增量**加入 Production Identity Manifest，
  由既有 IC Selector 查詢 API 搜尋與詳情顯示。

兩個 PR **均不因本文件自動取得合併、燒錄或部署批准**。

## 凍結批次

| 檢查 | Source-locked result |
|---|---|
| 原始五組 CFG Phase 1 Research | 2,563 ICPN；成員 SHA `0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a` |
| 本次加入 IC Selector 的普通 SAM L10/L11 商業訂購碼 | **122** |
| 原廠 MCP 有身份、但 PDF 一般訂購碼未涵蓋的 VAO | **4，不收錄** |
| 122-row canonical CSV SHA-256 | `2cc6aefd029edbb6438c300d485d4df8b639f41c099b168f216f31c31165593e` |
| 122-row canonical CSV Git blob SHA | `0eb9c765e78e93686629b17576b122a14dfa60ab` |
| 122 Exact ICPN 集合 SHA-256（排序，一行一筆） | `7a75e18a5f23cc2b80e10e1675918ce7da0601fe0d8d35664ebb78c4fb8d3b64` |
| 原廠 DS60001513G PDF 原始 SHA-256 | `ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e` |

Catalog 預期 4,853 → **4,975**：

- ST 原有 4,629 不變；
- NXP 原有 224 不變；
- Microchip 新增 122，並且全數 `mapping_status=no_mapping`、
  `openocd_target_config=""`、無其他可執行 Provider。

研究資料 `tcl/target/atsaml1x.cfg` 是 **OpenOCD CFG 線索**，
不能抄到 Product `openocd_target_config` 或當成已通過燒錄資格。

## IC Information

對這 122 筆保留對應欄位的分層證據：

- `VERIFIED`：原廠精確商業 ICPN／Base，以及雙來源適用性核對的
  Package、Pin Count、Main Flash、RAM、溫度等級與 Core Model。
- `PARTIAL`：Working VDD 只有原廠家族／Base Chart 線索，
  不能當成特定料號的已驗證燒錄電壓。
- `UNKNOWN`：I/O Supply、VDDA、Core Architecture。
- `S1_complete=0`，即使料號已在 Production IC Selector 可查詢，也
  不代表所有 Phase 1 電氣規格欄位完整。

原廠 PDF 提供訂購**規則**，並非直接列出所有 122 個完整商業料號；
Exact ICPN 存在性來自**原始 Microchip MCP**。
此交叉來源的 `VERIFIED` 解讀必須由 #921 審核通過。

## 產品與安全斷言

- IC Selector `/api/devices/search` 可依精確 ICPN 查詢
  原廠料號、六項資訊、來源證據狀態；使用原有 **exact-first**
  搜尋排序，若代碼同時也是較長訂購碼的 Prefix，
  `total_count` 可以大於 1，但首筆必須為 Exact ICPN。
- 任何四筆 VAO 特殊料號不以 Source-unknown 的猜測補收錄。
- Microchip 沒有實際命中的 OpenOCD 執行映射，因此
  `backend_providers=[]`、`selected_profile=null`，
  Phase 2 `UNKNOWN`。
- 工程 Job／Batch 的 `target_device` 不得引用這 122 筆建立執行綁定；
  不帶 `target_device` 的原始 Job `target` 字串同樣必須拒絕。
- ST／NXP API、來源 SHA、原本的 OpenOCD Provider、
  362 筆 H5／C5 Research-only Candidate 與歷史 ST Replay
  必須維持原本的資料與語意。

## ADR-0002 唯一政策：Phase 1 IDENTIFIED 即可查詢

[ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
2026-10-15 已正式採用：**原廠獨立證實完整商業 Exact ICPN 的
Phase 1 `IDENTIFIED` 是唯一 IC Selector 可見性資格**。
`INFORMATION_COMPLETE`、內部 Production Admission 批次、
是否有 OpenOCD CFG、Phase 2 `SUPPORTED`、Phase 3 HIL
均**不是 Phase 1 可見性的額外證據門檻**。

**122 筆只是現有 Production Manifest 的第一批工程部署增量，
不是另一種 Phase 1 研究分級，更不是排除其餘原廠已驗證 ICPN 的理由。**
目前限定快照內 23,276 筆原廠 Exact ICPN 已通過 Phase 1
`IDENTIFIED`，其中凍結 5-CFG 子集合 2,563 筆；本 PR 將其中
122 筆接到正式 Catalog，仍有 **23,154 筆已 IDENTIFIED 尚未在
Product IC Selector 上線**。這是跨 Brand canonical Phase 1
可見性部署缺口，不是原廠身份或資訊完整度不合格。

舊版文件所稱「未來 SUPPORTED-only Selector 政策」
已被最新 ADR-0002 取代，不得再做為 Microchip 開發依據。
#924 只處理當前 122 筆受測試保護的增量；
後續 migration 必須沿用相同身份證據門檻，完整追蹤
`/api/devices/search`、`catalog_size`、`total_count` 與分頁，
不得隱藏其他已確認的 Exact ICPN。

P0／P1／P2 等歷史來源群組僅供原始資料重播與 SHA 稽核，
不屬於現行 Phase 1／2／3 分類，也不得寫入 UI 的正式狀態欄位。

Selector 可查詢不代表可燒錄：Job／Batch 始終需要 Phase 2
`SUPPORTED`、正確 Runtime、電氣與 Site 安全限制並 fail-closed。

## 驗收

提交分支不等於正式上線。只有在原廠來源 SHA 重播通過、
122 筆完整檢索／負向測試通過、ST／NXP 回歸測試通過、
TypeScript/UI 編譯與完整 CI 通過，並取得另一次 owner
合併批准後，才可合併；部署還須獨立執行。
