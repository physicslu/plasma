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
  正式來源證明的 Exact ICPN 加入 Production Identity Manifest，
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

## ADR-0002 必須獨立決策的議題

[ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
目前的最終政策文字表示預設公開可選 Catalog 應以 Phase 2
`SUPPORTED` 過濾；而目前 ST／NXP 已提供未有軟體資格的
Phase 1 Production Identity 查詢，遷移由 Issue #849 追蹤。
**兩者仍未完成政策一致性修訂**。

本 PR 保持既有行為，並將 Phase 1 Search 與 Job／Batch
執行權限分開。不能把修改測試分母誤解成已獲批准更改 ADR
或預設可燒錄選料政策；後續需另行核准政策及介面入口分離。

## 驗收

提交分支不等於正式上線。只有在原廠來源 SHA 重播通過、
122 筆完整檢索／負向測試通過、ST／NXP 回歸測試通過、
TypeScript/UI 編譯與完整 CI 通過，並取得另一次 owner
合併批准後，才可合併；部署還須獨立執行。
