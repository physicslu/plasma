# 交接：Legacy Gateway Batch 退場清冊（PR-F，2026-11-12）

狀態：工程交接文件。本文件不授予任何 Gate 1 範圍、硬體操作、部署或合併權限；
這些仍依 [AGENTS.md](../../../AGENTS.md) 的 Gate 1 / Gate 2 規則。

契約依據：[Unified Programming Architecture v1](../../architecture/unified-programming-architecture-v1.md) §11。
來源稽核：[Gate 1 唯讀 Gap Audit](2026-11-12-unified-programming-architecture-gate1-audit.md)。

基準：`origin/main` = `353cadcca`（PR #1406 合併於 #1410 之上，2026-11-12 12:50 +0800）。
本清冊由唯讀依賴稽核產出，未修改程式、未部署、未操作 Z2/DUT。

---

## 0. 退場規則（owner 決策 D-2，normative）

1. **不得整批刪除。** 每一個 consumer 逐一判定 **刪除／遷移／保留**。
2. PR #1406 不 revert，其 Merge Commit 與 CI Evidence 保留為歷史紀錄。
3. `.codegraphignore`、`AGENTS.md` 的 CodeGraph 區塊、Playwright CI timeout 15 分鐘已在 main，直接沿用。
4. Read Memory 的功能契約與有效測試案例**必須保留**，執行路徑改走 Manager-owned Read Job。
5. Mock/CD **必須保留**，逐步改由統一 Manager Programming Engine 執行。
6. **PR-F 完成前，不得在任何文件、UI 文案、PR 描述或報告中宣稱 Legacy Gateway Batch 已退場。**

### 0.1 不在本清冊範圍：alias-scoped Manager Batch API（owner 決策 B-d，2026-11-13）

`POST /ppus/<alias>/programming/batches` **不屬於**本清冊的 Legacy Gateway Batch 範圍。
它是 Manager-owned 路徑的一部分，被 PR-B 新增的 canonical `POST /programming/batches`
取代，而不是被判定為 legacy。

其退場責任明確**從 PR-F 移至 PR-C**。PR-B 保留它為短期相容入口且不修改 `software/web`；
PR-C 完成 Consumer 遷移與下列 Gate 後直接移除，條件見
[架構契約 §5.8](../../architecture/unified-programming-architecture-v1.md)：
Consumer Inventory（EMode／PMode／Console BFF／CLI 與 scripts／API clients／測試與 fixtures／
已部署的 SWPC Control Station）、start 與 status／query 與 stop 與 reconcile 與
error／outcome handling 全數遷移、host-only regression 與 API contract 與 Console E2E 通過、
以及明確的部署順序。

**Console 原始碼已切換不等於已部署的 consumer 已遷移。** 任何無法確認的外部 consumer
列為明確阻塞項，舊端點就留著。

---

## 1. 擋住排程的發現

> **2026-11-12 更正。** 本節原為「兩個發現」。PR-B1 實作時找到第三個（P0-C），
> 是 Gate 1 唯讀稽核沒有抓到的。

### P0-A — Mock 介面的 `operations[]` 語意偏離

> **2026-11-12 更正。** 本節原本寫「Mock 缺 `run_operations`，收到 `programming` 會直接失敗」。
> 字面成立（`mock.py` 自己沒有這個方法），但機制敘述錯誤，而且方向相反 ——
> `BaseInterface.run_operations` **有**預設實作，Mock 繼承它，所以不是 fail-closed。

`plasma_handlers/programming.py` 的 `Operation.PROGRAMMING` 分支呼叫 `interface.run_operations(...)`。

| 介面 | `OPERATIONS` 集合 | `run_operations` |
| --- | --- | --- |
| `plasma_interfaces/openocd.py` | 有（`FLASH_CYCLE`／`PROGRAMMING`／`READ`） | 覆寫 |
| `plasma_interfaces/mock.py` | 無（不需要；只有 openocd 分支會查） | 繼承 Base 預設 |

Base 預設依序呼叫自己的 `erase`／`program`／`verify`，因此 Mock Site 會**跑完並回報成功**，但：

1. 寫在偏移 0，而不是 Job Binding 的位址 —— 預設實作的簽章根本不帶位址。
2. 擦掉整片模擬裝置，而不是 Image 的擦除視窗。
3. 回傳 `{}`，沒有 `steps`、沒有 `result`、沒有 `safe_off`。

Manager `_verify` 的第一道檢查是 `safe_off is True`，所以最終仍會 FAIL，但是以
`SAFE_OFF_NOT_VERIFIED` 而非 `OPERATIONS_MISMATCH`，且是在裝置已被錯誤寫入之後。

處置：獨立成 **PR-B1**，排在 PR-D 之前。這是硬前置，不是「逐步遷移」的一部分。

### P0-B — `server-batch-api.ts` 不能整檔刪除

`software/web/app/fleet/managed-factory-backend.ts` 匯入它的
`BatchSiteSnapshot` / `ServerBatchSiteState` / `ServerBatchSnapshot` / `ServerBatchState`。
那是 **managed** PMode 路徑，不是 legacy。

處置：拆成「HTTP client（刪除）」與「snapshot 型別（遷移）」兩半。

### P0-C — `enqueue` 在 admission 之前就擋掉帶 Provider metadata 的 Job

> 2026-11-12 PR-B1 實作時發現，Gate 1 唯讀稽核未抓到。

`plasma_server/site_manager.py` 的 `enqueue` 在 `_admit_job_binding` **之前**有一道閘：
任何帶 `provider` metadata 的 Job，若該 Site 不是「就緒的 OpenOCD」，一律以
`PROVIDER_JOB_NOT_AUTHORIZED` 拒絕。

Job Binding 的身分包含 `provider` 與 `profile`，所以**任何** Binding Job 都必然帶這兩個欄位。
結果是 Mock Site 連 Binding 都送不進去，這道閘比 P0-A 更早觸發。

處置（PR-B1 已做）：改以介面能力判定而非 `isinstance` 鏈 ——
`BaseInterface.CONSUMES_JOB_BINDING` 宣告該介面是否執行已 admit 的 Binding，
`enqueue` 放行「宣告消化 Binding 且確實帶 Binding」的 Job。C-3 的 bundle-reference
`flash_cycle`（無 Binding）維持原分支。既有的允許／拒絕集合未因此縮小或擴大到其他情形。

---

## 2. Web Console 層

| 檔案 | 判定 | 依據 |
| --- | --- | --- |
| `app/engineering/programming-workspace-v2.tsx` · `StandaloneProgrammingWorkspace` | **遷移** | mode 分派點保留；#1406 的 per-Site Read 按鈕行為契約依規則 4 保留，執行改走 `runManagedRead` |
| `app/engineering/engineering-server-batch.ts` | **刪除** | 唯一 consumer 是 EMode standalone |
| `app/server-batch-api.ts` | **拆**：client 刪除、型別遷移 | 見 P0-B |
| `app/server-batch-snapshot-store.ts` | **刪除** | 唯一 consumer 是 `server-batch-api.ts` |
| `app/batch-execution-activity.ts` | **遷移** | `app/global-nav.tsx` 的全域活動指示在用，改接 Manager Batch |
| `app/batch-readiness.ts` | **遷移** | `app/operator-ui/programming-job-panel.tsx`（兩模式共用的設計系統元件）在用 |
| `app/fleet/factory-console-v2.tsx` unmanaged 分支 | **遷移** | 統一到 managed 路徑 |
| `app/plasma-api.ts` | **保留，逐項覆核** | Mock/CD 與診斷仍需；非整檔問題 |

## 3. Manager relay allowlist

位置：`software/python/plasma_manager/server.py` 的 `_MANAGED_GET_PATTERNS` / `_MANAGED_POST_PATTERNS`。

| 樣式 | 判定 |
| --- | --- |
| GET `^/api/batches/{seg}$` | **刪除** |
| POST `^/api/batches$` | **刪除** |
| POST `^/api/batches/{seg}/cancel$` | **刪除** |
| POST `^/api/batches/{seg}/targets/{seg}/{seg}/cancel$` | **刪除** |
| POST `^/api/jobs$`、`^/api/jobs/{seg}/cancel$` | **逐項覆核** |
| GET `^/api/jobs/{seg}/files/{seg}$` | **逐項覆核**（Read 下載） |
| `/api/engineering/targets/...` 系列（status／jobs／programming-assets／files） | **逐項覆核** |

覆核理由：Manager-owned 流程**不經過這條 relay** —— Manager 以自己的 PPU client 直接送 Job。
這份 allowlist 服務的是 Browser → Manager → PPU 的 pass-through，所以 `/api/jobs` 系列很可能同屬
legacy，但必須先確認 Mock/CD 與診斷是否依賴，才能判定。

## 4. PPU Gateway batch runtime

路由入口在 `software/python/plasma_web/gateway.py`（`api/batches` 前綴判斷）。

| 檔案 | 判定 |
| --- | --- |
| `plasma_web/mock_batch_runtime.py` | **遷移優先** — Mock/CD 的執行引擎 |
| `plasma_web/persistent_mock_batch_runtime.py` | **遷移優先** — 同上 |
| `plasma_web/batch_runtime.py` | **刪除候選** |
| `plasma_web/durable_batch_runtime.py` | **刪除候選** |
| `plasma_web/persistent_batch_runtime.py` | **刪除候選** |
| `plasma_web/batch_state_store.py` | **刪除候選** |

四個刪除候選在動手前，必須先確認未被 PPU 自主恢復流程使用。
**Mock/CD 遷移（PR-B1 + PR-D）完成前，六個檔案一律不得刪除。**

## 5. Mock/CD — 全數保留

21 個檔案，依規則 5 保留，執行引擎依 P0-A 遷移：

* workflow：`.github/workflows/mock-cd.yml`、`.github/workflows/mock-cd-browser.yml`
* 腳本：`scripts/mock-cd.py`、`scripts/mock-cd-browser-stack.py`
* 文件：`docs/architecture/mock-runtime-v1.1.md`、`docs/development/mock-cd.md`、
  `docs/development/mock-runtime-foundation-notes.md`、`docs/development/mock-runtime-operator-guide.md`
* Runtime：`software/python/plasma_web/mock_runtime_settings.py`
* Console：`software/web/app/mock-runtime-api.ts`、`software/web/app/engineering/mock-runtime-settings.tsx`、
  `software/web/app/engineering/mock-runtime-settings.css`
* 測試：`test_mock_cd_contract.py`、`test_mock_cd_browser_contract.py`、
  `test_mock_runtime_foundation.py`、`test_mock_runtime_settings.py`、
  `software/web/tests/mock-runtime-contract.test.mjs`、
  `software/web/e2e/playwright.mock-cd.config.ts`、`mock-cd-runtime.spec.ts`、
  `mock-runtime-settings.spec.ts`、`mock-runtime-settings-runtime.spec.ts`

## 6. 測試層 — 逐項判定

### Python（15 支）

`test_batch_mock_integration.py`、`test_batch_runtime.py`、`test_batch_runtime_contract.py`、
`test_batch_web_gateway.py`、`test_c3_rest_flash_cycle.py`、`test_gateway_durable_batch_wiring.py`、
`test_lom_p2a2_gateway_g13.py`、`test_main_flash_read_contract.py`、`test_manager_device_selector.py`、
`test_manager_managed_ppu_relay.py`、`test_mock_cd_browser_contract.py`、`test_mock_synthetic_image.py`、
`test_persistent_batch_recovery.py`、`test_runtime_acceptance_framework.py`、
`test_swpc_z2like_managed_programming_ingress.py`

### Web host（14 支）

`engineering-navigation-groups-contract`、`engineering-programming-v2-contract`、
`engineering-server-batch-ownership-contract`、`factory-live-density-contract`、`fleet-ui-contract`、
`gateway-settings-contract`、`legacy-ui-retirement-contract`、`mock-runtime-contract`、
`production-operation-guidance-contract`、`programming-job-active-controls-contract`、
`programming-job-control-design-system-contract`、`server-batch-api-contract`、
`unified-batch-dashboard-contract`、`unified-managed-programming-contract`

> `legacy-ui-retirement-contract.test.mjs` 本身就是退場守衛：**擴充，不是刪除**。

### E2E（11 支）

`engineering-log-observability`、`engineering-operator-audit-log`、
`engineering-programming-asset-cache-runtime`、`engineering-programming-v2`、`engineering-programming`、
`factory-production-console`、`mock-cd-runtime`、`mock-synthetic-image`、`mode-switch-execution-guard`、
`production-kpi-snapshot`、`production-multi-ppu-runtime`

### 測試判定規則

1. 斷言 **legacy 傳輸路徑**（`/api/batches`、直連 Gateway）的案例 → 隨該路徑刪除。
2. 斷言 **行為契約**（Read Memory 獨立 Job、E/P/V 固定順序、PASS 需 SAFE_OFF、停止即停排隊）
   的案例 → **保留**，改寫成對統一引擎的斷言。
3. Mock/CD 的案例 → 全部保留。
4. 以正則比對原始碼字面的 source-level 契約測試（#1406 新增數支）→ 隨被比對的程式一起更新，
   不得只為通過而放寬斷言。

---

## 7. PR-F 執行順序

1. PR-B1 完成（Mock 支援 `operations[]`）
2. PR-D 完成（PMode 切換、`execution_router` 限制解除）
3. 第 2 節「遷移」項目逐一搬家，測試依第 6 節規則改寫
4. 第 2～4 節「刪除」項目移除，`legacy-ui-retirement-contract` 擴充為守衛
5. 全部完成後，才可移除本文件第 0 節第 6 點的限制

## 8. 未決

* 第 3 節「逐項覆核」的 allowlist 條目尚未判定。
* alias-scoped Batch API 的完整 Consumer Inventory 由 PR-C 產出（見 §0.1）；本清冊不負責。
* 第 4 節四個刪除候選與 PPU 自主恢復流程的關係尚未查證。
* Device Personalization（PR-G）對本清冊無直接影響，但其 Profile schema 須與 `flash_cycle`
  退場合併為同一次 Profile 改版，見架構契約 §8.6。
