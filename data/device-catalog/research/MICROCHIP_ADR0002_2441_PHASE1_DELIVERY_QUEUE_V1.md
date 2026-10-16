# Microchip Phase 1：剩餘 2,441 筆 Exact ICPN 交付佇列

## 工程目標與 ADR-0002

以已合併的 ADR-0002 為唯一 Phase 1／2 標準。Microchip 這一階段的工程目標是五組 OpenOCD Target CFG 反查，並經原廠 MCP 商業料號身分驗證的 **2,563 筆 Exact ICPN**。

| 項目 | Exact ICPN | 性質 |
| --- | ---: | --- |
| 本階段 Phase 1 目標 | **2,563** | 五組 CFG 的凍結目標 |
| #921／#924 第一批 | **122** | 原廠 MCP 與 DS60001513G 六項欄位交叉驗證的普通訂購碼 |
| **本 PR 剩餘佇列** | **2,441** | 凍結 2,563 扣掉精確 122 個 ICPN |
| 其他已確認原廠來源料號 | 20,713 | 本階段範圍外；不撤銷 Phase 1 身分 |
| Phase 2 SUPPORTED／Phase 3 PASSED | **0／0** | CFG 線索不授權燒錄或 HIL |

### 依五組 CFG 劃分後續工作

| OpenOCD CFG 研究線索 | 待交付 |
| --- | ---: |
| tcl/target/pic32mx.cfg | 1,241 |
| tcl/target/at91samdXX.cfg | 667 |
| tcl/target/atsame5x.cfg | 354 |
| tcl/target/atsamv.cfg | 175 |
| tcl/target/atsaml1x.cfg | 4 |
| **總計** | **2,441** |

剩下 **四筆 VAO 特殊後綴**已有原廠精確料號證據，仍是 Phase 1 IDENTIFIED；但一般 PDF 訂購碼規則未涵蓋該後綴，因此不能將相關封裝、溫度及其他未確認欄位自行提升為 VERIFIED。

## 可重播原廠證據與輸出

Python 程序 microchip_adr0002_phase1_remaining2441_queue_v1.py 經 CI 使用下列已凍結來源交叉確認：

1. 原廠 MCP 23,276 筆 Exact ICPN 身分來源，包含原始回應 SHA-256、觀察時間與來源 scope。
2. 五組 CFG 的 2,563 筆身分／Base／CFG 集合，其凍結 SHA-256 為 0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a。
3. Microchip DS60001513G 官方 PDF 原始 SHA-256 ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e 與 126 筆原廠 MCP 的訂購碼交叉檢查。
4. 第一批 122 個精確料號名稱集合 SHA-256 為 7a75e18a5f23cc2b80e10e1675918ce7da0601fe0d8d35664ebb78c4fb8d3b64，僅扣除此 122 個 exact code，不依 family/prefix/資料完整度猜測。

Git 倉庫另保留 **data/device-catalog/research/microchip-phase1-remaining2441-exact-identity-v1.csv**，包含 2,441 筆精確商業料號、Base、原廠 URI／scope／SHA、來源觀察時間與 CFG 研究線索及 Phase 2／3 狀態。
此來源索引的原始 CI 重播 SHA-256 為 **ecec8112d52d3d5b3b7313e2316da67e6dc670794713abf49b5b8fdeb6f0688d**。CI 會重新產生 CSV，逐位元組比較已提交 Git 的檔案，禁止來源漂移。

輸出兩個主要 Research artifact：
- microchip-adr0002-phase1-remaining2441.jsonl：每筆原廠身份、十三欄資料及 VERIFIED／PARTIAL／UNKNOWN／CONFLICT／NOT_APPLICABLE 狀態、source、SHA、CFG research-only lead。
- microchip-adr0002-phase1-remaining2441-summary.json：逐 CFG、逐欄位狀態分布、完整來源佇列 SHA-256 與安全宣告。

未知欄位不能補零，家族資料不能冒充精確 SKU VERIFIED。CFG research-only lead 不是可執行映射，也不能取得 Phase 2 SUPPORTED 或 Phase 3 PASSED。

## 尚未完成的上線工程

**此 PR 建立 2,441 筆原廠證據與欄位狀態的可重播 Phase 1 待交付資料佇列，不直接寫入 Production Catalog。** 後續仍須正式 Canonical Store 持久化、Production Admission 與可空欄位 schema、IC Selector API／UI／總數與分頁、Job／Batch fail-closed 全數負向測試，以及合併與部署批准。

CI 90 天 artifact 不是永久來源庫；正式部署之前必須解決來源保管鏈。其餘 20,713 筆來源身份資料不因本階段 2,563 目標而被改為不合格。
