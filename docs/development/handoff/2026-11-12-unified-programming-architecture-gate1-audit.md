# 交接：Unified Programming Architecture Gate 1 唯讀 Gap Audit（2026-11-12）

狀態：工程交接文件。本文件不授予任何 Gate 1 範圍、硬體操作、部署或合併權限；
這些仍依 [AGENTS.md](../../../AGENTS.md) 的 Gate 1 / Gate 2 規則。

本稽核全程唯讀：未修改程式、未建立 PR、未部署、未操作 SWPC/Z2/DUT，
未更動共用 repo checkout 的既有 Dirty Worktree。

每項結論標註 **CONFIRMED**（已在原始碼或執行環境證實）/ **INFERRED**（由證據推論）/
**NOT_VERIFIED**（本次未查證）。

---

## 0. 基準

| 項目 | 值 | 標註 |
|---|---|---|
| `origin/main` HEAD | `3d6f3c6b2ff4e874128c5882d47daaf35d5ab98d`（Merge PR #1409，2026-11-12 10:36 +0800） | CONFIRMED |
| PR #1406 HEAD | `04b1c049aeca2dc7f5f7651d95d1ecf5f99d03ca`（Draft、base `main`、14 檔 +110/−30） | CONFIRMED |
| #1406 merge-base | `3d6f3c6b2ff4…`（已 rebase 到目前 main，無落後） | CONFIRMED |
| 本地共用 repo checkout | `b74a9893e`（branch `engineering-programming-ui-cleanup-gate1`，8 檔 Dirty）— 未觸碰 | CONFIRMED |
| 稽核讀取來源 | 兩個 clean worktree：一個在 `3d6f3c6b2ff4`（= origin/main），一個在 `04b1c049a`（= #1406 HEAD） | CONFIRMED |
| SWPC Control Station 線上版本 | `~/.local/share/plasma/local-control-station/releases/3d6f3c6b2ff4`（= origin/main，2026-11-12 11:17 部署） | CONFIRMED |
| Z2 Runtime | 本次未連線查證 | NOT_VERIFIED |

---

## A. Executive Summary

1. **已經存在一套共用的 Manager Programming Engine**，EMode 與 PMode 都走它：
   `runManagedProgramming` / `runManagedBatch` → BFF → `plasma_manager/programming.py` plan+run → PPU `/api/jobs`。
   `software/web/app/programming/managed-programming.ts:1-8` 明確宣告
   「One formal data path for both product modes」。**CONFIRMED**

2. **但三個關鍵層級仍然分叉**，這才是本次架構工作的真正範圍：
   - **Target Scope**：EMode 目前是「單 PPU **單 Site**」（不是單 PPU 多 Site）；PMode 是「多 PPU 多 Site」但 Batch 在瀏覽器。
   - **Batch Ownership**：EMode 有 Manager-owned、持久化、可對帳的 Batch（`programming_batch.py`）；PMode 只有 Browser-owned、重新整理即消失的 `ManagedProductionBatch`。
   - **Operations 模型**：EMode 用新的 `operations[]`（programming Job）；PMode **只用 legacy `flash_cycle`**。

3. **最大的單一技術風險不是程式碼，是 Programming Route 的 Resource Set 身分**。
   目前 repo 只有兩條 Route，且兩條的 Profile 不同、Resource Set SHA 不同：
   - `z2-site2-stm32f103c8t6`（`operations: ["flash_cycle"]`）
   - `z2-site2-stm32f103c8t6-operations`（`operations: ["erase","program","verify","read"]`）

   把 PMode 從 `flash_cycle` 切到 `operations[]` **會改變 Resource Set**，
   導致每台 PPU 的 `resource_reuse=false`，強制跑 B1/B2/B3 重新 Activate。
   這是 P0 阻塞項，必須在 PR-A 先決策。
   **CONFIRMED**（`data/opf/programming-routes/*.json`；`programming.py:434-640` plan 的 reuse 判定）

4. **PMode 確實以「第一台 PPU 的 Route」作為全域資格** —— 但只在 **UI gating**，
   執行時的 Admission 是逐 PPU 重新觀測的。這個區分很重要：是 UI 正確性缺陷，不是安全缺陷。
   **CONFIRMED**（`factory-console-v2.tsx:680-682` vs `managed-factory-backend.ts:221-227`）

5. **PR #1406 與新架構的重疊極小**：它只動 `StandaloneProgrammingWorkspace`
   （非 managed 的 Legacy 直連 Gateway 路徑）與測試，完全沒碰 `managed-programming.ts`、
   `managed-programming-workspace.tsx`、`factory-console-v2.tsx`、`plasma_manager/*`。
   只有 3 個檔案有未來衝突面。**CONFIRMED**

6. **八通道並行：無任何實機證據**，且目前架構三層都在循序化
   （Manager per-alias、PMode 瀏覽器全域循序、PPU `max_concurrent_jobs` 預設 2）。
   本次架構工作**不應**宣稱或預設啟用並行。**CONFIRMED / NOT_VERIFIED（硬體）**

---

## B. EMode / PMode Difference Matrix

| 維度 | EMode（managed） | PMode（managed） | 證據 | 標註 |
|---|---|---|---|---|
| UI 入口 | `ManagedProgrammingWorkspace` | `FactoryConsoleV2` | `programming-workspace-v2.tsx:236`；`factory-console-v2.tsx:432` | CONFIRMED |
| PPU Scope | 單 PPU（`selectedAlias`） | 多 PPU（`batchTargets` flatMap） | `managed-programming-workspace.tsx:290,530`；`factory-console-v2.tsx:822-826` | CONFIRMED |
| Site Scope | **單 Site**（`chosenSiteId`，註解「One Site, one Job」） | 多 Site | `managed-programming-workspace.tsx:342,350,580` | CONFIRMED |
| Operations | `operations[]`（E/P/V 固定序） | **僅 `flash_cycle`** | `managed-programming-workspace.tsx:355`；`factory-console-v2.tsx:909` + `bundle-programming-api.ts:42` | CONFIRMED |
| Read Memory | 獨立 per-Site Job，不入 Batch | **完全沒有**（`.filter(isImageOperation)` 濾掉） | `managed-programming-workspace.tsx:710-757`；`factory-console-v2.tsx:908-909` | CONFIRMED |
| Batch Owner | Manager（`ProgrammingBatchCoordinator`） | Browser（`ManagedProductionBatch`） | `programming_batch.py:111`；`managed-factory-backend.ts:149` | CONFIRMED |
| Batch 持久化 | JSON journal + fsync + 重啟復原 | 無，reload 即失 | `programming_batch.py:166-184,128-165`；`managed-factory-backend.ts:12-14` | CONFIRMED |
| Batch Identity | `batch_id`（Manager `secrets.token_hex(16)`） | `console-<ts>-<rand>`（瀏覽器產生） | `programming_batch.py:273`；`managed-factory-backend.ts:150` | CONFIRMED |
| start_id / Idempotency | `issue_batch_start` → `consume_batch_start`，一次性 | 無 Batch start_id；run 用 `plan_id` 當 start_id | `programming.py:683-736`；`managed-programming.ts:534-537` | CONFIRMED |
| Start Outcome 對帳 UI | 有（hold / reconcile / void / acknowledge） | **無** | `managed-programming-workspace.tsx:218,438,457-510`；`factory-console-v2.tsx` 無 `startHolds` | CONFIRMED |
| Retry | Manager Retry（0–5，條件嚴格） | **固定 0**，永不重送 | `programming_batch.py:67-108,334-413`；`managed-factory-backend.ts:11,334` | CONFIRMED |
| Repeat | 固定 1（`400 repeat_not_supported`） | 固定 1 | `programming_batch.py:67-72`；`managed-factory-backend.ts:352` | CONFIRMED |
| Stop Policy | `{never}` 或 `{failed_sites, threshold:1}` | `failedSiteStopThreshold: number \| null` | `programming_batch.py:76-86`；`managed-factory-backend.ts:128,299-305` | CONFIRMED |
| Stop 語意 | Manager「停止排隊」，不取消已送出 Job | Browser「停止排隊」，不取消 | `programming_batch.py:308-322`；`managed-factory-backend.ts:173-180` | CONFIRMED |
| OUTCOME_UNKNOWN | Manager latch 整台 PPU，須 acknowledge | 僅 session 內 skip 同 PPU 後續 Site | `programming.py:372-377,640-657`；`managed-factory-backend.ts:293-297` | CONFIRMED |
| 併發 | 一次一 run（per alias） | 全域嚴格循序（跨 PPU 也不平行） | `programming.py:378-382`；`managed-factory-backend.ts:9-10,211` | CONFIRMED |
| Route 資格來源 | 每個選定 alias 各自載入 | **第一台 PPU** 的 Route 作全域 UI gating | `managed-programming-workspace.tsx:313-318`；`factory-console-v2.tsx:680-682` | CONFIRMED |
| 執行時 Admission | plan 時逐次驗證 | 逐 PPU 重新觀測（正確） | `programming.py:539-570`；`managed-factory-backend.ts:221-227,276-291` | CONFIRMED |
| Readiness 模組 | 自有 `readiness` 計算 | `evaluateBatchReadiness`（legacy 共用） | `managed-programming-workspace.tsx:359-400`；`factory-console-v2.tsx:890` | CONFIRMED |

---

## C. 完整 Call Graph

### C-1. EMode Programming Batch（Manager-owned，現況）

```text
[Console] managed-programming-workspace.tsx:588 startBatch()
  └─ :612 runManagedBatch(request)                    managed-programming.ts:646
       ├─ issueBatchStart(alias)                      bundle-programming-api.ts:425
       │    └─ POST /api/manager/registry/{alias}/bootstrap/programming/starts
       └─ startProgrammingBatch(alias, input, startId) bundle-programming-api.ts:349
            └─ POST .../bootstrap/programming/batches
[BFF] app/api/manager/registry/[...path]/route.ts:33-39  → bootstrap-bff.ts
      POST allowlist: /^programming\/batches$/ :31 ; /^programming\/starts$/ :35
      GET  allowlist: /^programming\/batches\/{32hex}$/ :45 ; starts/{id} :47
[Manager] bootstrap_server.py:546 → _batches().start(alias, body)
          bootstrap_server.py:556 → _programming().issue_batch_start(alias, body)
[Coordinator] programming_batch.py:236 start()
   ├─ workflow.require_batch_start()        programming.py:717
   ├─ workflow.plan(alias, plan_body)       programming.py:434   ← Route 解析 / Bundle v3 / Resource 比對 / Job Binding
   ├─ workflow.consume_batch_start()        programming.py:725   ← journal 先寫
   └─ _run_attempts()                       programming_batch.py:334
        └─ workflow.start(plan_id, "PROGRAM")  programming.py:638
             └─ _execute(run, plan)            programming.py:897
                  ├─ _readiness()               programming.py:348   GET /api/health/ready, /api/status?site=
                  ├─ _activate()  (僅 reuse=false) programming.py:946  B1 upload → B2 admit → B3 activate(fpga_load=false)
                  ├─ _submit_once()             programming.py:1028  POST /api/jobs  (operations[] 或 operation)
                  ├─ _poll_job()                programming.py:1071  GET /api/status?job=
                  └─ _verify()                  programming.py:1169  Receipt v3（SAFE_OFF / Binding / 每步 range+SHA）
[PPU Runtime] site_manager.py:204 _reserve_execution_job → PPUExecutionLease
              execution_router.py:60 resolve_route → OPENOCD_ROUTE
              plasma_handlers/programming.py → plasma_interfaces/openocd.py:142 run_operations
```

### C-2. EMode Read Memory（獨立 per-Site Job）

```text
managed-programming-workspace.tsx:757 runManagedRead
  → managed-programming.ts:578 planProgramming({operation:"read", address, length})
  → startProgramming → observeRun
  → getReadOutput(alias, runId)        bundle-programming-api.ts:288
     → GET .../bootstrap/programming/runs/{id}/output   bootstrap-bff.ts:41
     → bootstrap_server.py:311 → programming.py:1144 read_output()  （Manager 重新 SHA256）
```

### C-3. PMode Production Batch（Browser-owned，現況）

```text
[Console] factory-console-v2.tsx:1091 executeManagedBatch()
  └─ new ManagedProductionBatch({targets[], icpn, operation:"flash_cycle", file, threshold})
                                              managed-factory-backend.ts:149
       └─ :212 execute()  ← 嚴格循序，逐 Site
            ├─ :225 admit(alias)   → loadManagedTopology / loadPlatformAvailability / loadProgrammingRoutes
            └─ :244 runManagedProgramming({operation:"flash_cycle"})
                 → managed-programming.ts:484
                      planProgramming → startProgramming → observeRun
                      （之後與 C-1 的 Manager plan/run/_execute/_verify 完全相同）
  並行：:1121 pollServerBatch(batch.batchId)  ← 只讀瀏覽器自己的 snapshot()
```

### C-4. Legacy 直連 Gateway 路徑（EMode standalone + PMode unmanaged，PR #1406 的範圍）

```text
EMode: programming-workspace-v2.tsx:236 → StandaloneProgrammingWorkspace
       → engineering-server-batch.ts → /api/engineering/targets/{f}/{p}/api/batches
PMode: factory-console-v2.tsx:1127 createServerBatch → server-batch-api.ts
[Manager relay] server.py:327 _parse_managed_ppu_route → :843 _relay_managed_ppu_request
       POST allowlist: server.py:109 /api/jobs, :111 /api/batches, :113 .../cancel
       → PPU Gateway 自己的 Batch Runtime（Manager 不介入 plan / receipt）
```

> 關鍵觀察：**C-4 是第三套 Programming 路徑**，它完全繞過 Manager 的 Route Admission、
> Job Binding 與 Receipt v3。本次統一架構若不處理它，repo 內會同時存在三套。**CONFIRMED**

---

## D. Unified Architecture 與 API Contract（建議）

### D-1. Target Set

```jsonc
// 統一 Target Set：Mode 只決定 scope 約束與 UI，不決定資料結構
{
  "targets": [
    { "ppu_alias": "z2",  "site_ids": [1, 2, 3] },
    { "ppu_alias": "z2b", "site_ids": [2] }
  ]
}
```

| Mode | 約束 | 驗證點 |
|---|---|---|
| EMode | `targets.length === 1`，`site_ids.length >= 1` | Manager 側 `422 emode_single_ppu_required` |
| PMode | `targets.length >= 1` | 無額外約束 |

目前 `programming_batch.py:236` 的 `start()` 只接受 `site_id`（單數，來自 `PLAN_KEYS`，
`programming_batch.py:56`），`batch["site_id"] = planned["site_id"]`（:272）。
**統一後 `site_id` 必須升級為 `targets[]`，`parse_policy` 的 `threshold == 1` 硬限制（:80-81）同時解除。**

### D-2. Programming Operations

維持 [`opf-programming-operations-v1.md`](../../architecture/opf-programming-operations-v1.md)
已凍結的模型，**不新增語意**：

| Job kind | wire | 範圍 |
|---|---|---|
| `programming` | `operations: [...]`（erase→program→verify 固定序） | 每 Site 一個 Job，一個 Binding，一張 Receipt |
| `read` | `operation:"read"` + `address`/`length` | 獨立 per-Site Job，**不入 Batch** |
| `flash_cycle` | `operation:"flash_cycle"` | **legacy，保留不動** |

- Erase Only = `operations:["erase"]` + 明確 erase-aligned range（`bundle_v3.py:533-540`）。保留。
- `[erase, verify]` 永遠拒絕（`bundle_v3.py:298`）。
- Image / Bundle v3 雙來源保留（`programming.py:486-505`）。

**移除 PMode `flash_cycle` 專用路徑的影響分析：**

| 影響面 | 具體後果 | 標註 |
|---|---|---|
| Resource Set 身分 | PMode 改用 `-operations` Route → `resource_set_sha256` 改變 → `programming.py:566` `resource_reuse=false` → 每台 PPU 強制 B1/B2/B3 | CONFIRMED |
| Receipt 驗證 | `_verify` 的 `flash_cycle` 分支（`programming.py:1189-1196,1297-1303`）失去唯一消費者，但 `RECEIPT_OPERATIONS`（:71）仍含它 | CONFIRMED |
| Retry 資格 | `retry_eligibility`（`programming_batch.py:90-108`）與 operation 無關，不受影響 | CONFIRMED |
| PPU Runtime | `execution_router.py:68` 的 `PACKAGE_PROVIDER_ROUTE` **只接受 `Operation.FLASH_CYCLE`** — 若 PMode 走 OPF Package Provider，移除 flash_cycle 會直接 `OPERATION_UNSUPPORTED` | CONFIRMED |
| UI 契約測試 | `programming-job-test-helpers.ts` 的 `production: [...,"read"]`（#1406 新增）與新模型牴觸 | CONFIRMED |

**結論：Gate 1 建議「不移除 flash_cycle」**，改為「PMode 加 `operations[]` 支援，
flash_cycle 保留為 legacy，直到新模型通過 Site 2 HIL」。
這與 `opf-programming-operations-v1.md:22-24` 既有凍結文一致。

### D-3. Manager-owned Batch API

```text
POST .../bootstrap/programming/starts            → { start_id }           （已存在，kind=batch）
POST .../bootstrap/programming/batches           → { batch }              （需擴 targets[]）
GET  .../bootstrap/programming/batches/{id}      → { batch }              （已存在）
POST .../bootstrap/programming/batches/{id}/stop → stop queuing           （已存在）
GET  .../bootstrap/programming/starts/{start_id} → reconciliation（唯讀）  （已存在）
POST .../bootstrap/programming/starts/{id}/void  → 未入場才可 void         （已存在）
```

**跨 PPU 持久化 Batch 的 Identity 建議：**

```text
batch_id            : Manager 產生，32 hex
job_key             : (batch_id, ppu_alias, site_id, attempt_number)
start_id            : 一個 Batch 一個；Idempotency 的唯一憑證
plan_id / run_id    : 每個 attempt 各自一組（沿用現況）
```

排程：維持「一次一個 in-flight run」，但 scope 從「per alias」升級為
「per (alias)」+「全 Batch 的 round-robin 走訪」。
斷線恢復沿用 `_close_interrupted`（`programming_batch.py:145`）但需逐 Site 判定。

### D-4. Batch Policy 統一

| 欄位 | 統一預設 | 範圍 | 來源 |
|---|---|---|---|
| `repeat` | `1` | 固定 1（未實作 Repeat） | `programming_batch.py:67-72` |
| `retry_limit` | `0` | 0–5 | `programming_batch.py:73-76` |
| `stop_policy` | `{"kind":"never"}` | `never` / `{failed_sites, threshold: 1..N}` | `programming_batch.py:76-86`（解除 `threshold==1`） |

**不可協商的安全契約（已實作，必須原樣延續）：**

1. `OUTCOME_UNKNOWN` **絕不自動重送**，不消耗 retry 預算，latch 整台 PPU 直到 acknowledge
   （`programming_batch.py:14-16,383-385`；`programming.py:372-377`）。
2. `BLOCKED`（未送出）結束 Batch，不算 FAIL（`programming_batch.py:17`）。
3. 只有 **definite FAIL** 可重試，且必須 receipt 證明「恰好一次送出 + SAFE_OFF 已驗證 + Binding 一致」
   （`retry_eligibility`，`programming_batch.py:90-108`）。
4. 重試前必須 `retry_block()` 讀到 PPU 已釋放；任何讀不到的狀態一律封鎖（`programming.py:384-411`）。
5. Stop = **停止排隊**，永不取消已送出 Job、不釋放 lease、不清 recovery（`programming_batch.py:308-322`）。

### D-5. Programming Route Admission

每個 `(ppu_alias, site_id, icpn, operations[])` 各自 Admission：

```text
for each target.site:
    routes = load_routes(ppu_alias)                 ← 逐 PPU，禁止共用第一台
    matched = resolve_routes(routes, icpn, site, operations)
    if len(matched) == 0 → 422 operation_not_in_profile
    if len(matched)  > 1 → 409 programming_route_ambiguous
```

Manager 側已經是這個語意（`programming.py:539-558` 的 `resolve_routes` + ambiguity 拒絕），
**缺口只在 Console 的 UI gating**（`factory-console-v2.tsx:680-682`）。

### D-6. Receipt / Recovery

Receipt v3 已具備統一欄位，不需改 schema：
`job_id / job_state / operations / observed_operations / expected_steps / observed_steps /
safe_off / expected_job_binding_sha256 / observed_job_binding_sha256 /
expected_resource_set_sha256 / observed_resource_set_sha256 / read_output`
（`programming.py:1246-1275`）。

Batch 層只需新增 `per_site[]` 聚合，**不得**在 Batch 層重新判定 PASS
（`managed-programming.ts:715-728` 的 `batchVerdict` 已示範正確作法：
PASS 必須同時滿足 Batch outcome 與 last run receipt）。

---

## E. P0 / P1 / P2 Gap 清單

### P0（阻塞統一架構）

| # | Gap | 證據 | 標註 |
|---|---|---|---|
| P0-1 | **EMode Batch 只支援單一 Site**，無法多 Site | `programming_batch.py:3`（docstring「one PPU, one Site」）、`:56 PLAN_KEYS`、`:272 site_id`、`:80-81 threshold==1`；UI `managed-programming-workspace.tsx:342,350` | CONFIRMED |
| P0-2 | **PMode 無 Manager-owned Batch**：reload 即失、無 batch_id 持久化、無跨 PPU 排程 | `managed-factory-backend.ts:8-14,149-150` | CONFIRMED |
| P0-3 | **PMode 無 Batch start_id / Idempotency**：`startProgrammingBatch` 完全未被 PMode 使用 | `managed-factory-backend.ts:244`；`issueBatchStart` 僅 `managed-programming.ts:671` 使用 | CONFIRMED |
| P0-4 | **PMode 無 Start Outcome 對帳 UI**：`ManagedStartOutcomeUnknown` 只在 session 記憶體 latch | `managed-factory-backend.ts:264-266,293-297`；對帳 UI 僅在 `managed-programming-workspace.tsx:218,438,457-510` | CONFIRMED |
| P0-5 | **PMode 只跑 `flash_cycle`**，與 EMode 的 `operations[]` 分屬不同 Route / 不同 Resource Set | `bundle-programming-api.ts:42`；`factory-console-v2.tsx:909`；`data/opf/programming-routes/*.json` | CONFIRMED |
| P0-6 | **PMode UI 用第一台 PPU 的 Route 作全域資格** | `factory-console-v2.tsx:680-682`，被 `:909 managedOperationOptions`、`:923 managedBatchBlocker` 消費 | CONFIRMED |

### P1（正確性 / 一致性）

| # | Gap | 證據 | 標註 |
|---|---|---|---|
| P1-1 | **Policy 模型三套並存**：Manager `{repeat,retry_limit,stop_policy}` / PMode `{failedSiteStopThreshold}` / Legacy `{repeat_count,site_retry_limit,failed_site_stop_threshold}` | `programming_batch.py:67`；`managed-factory-backend.ts:128`；`server-batch-api.ts:24-28` | CONFIRMED |
| P1-2 | **PMode Retry 永遠 0**，連 Manager 已驗證安全的 definite-FAIL 重試都拿不到 | `managed-factory-backend.ts:11,334,353` | CONFIRMED |
| P1-3 | **PMode 無 Read Memory**（濾掉所有非 Image Operation） | `factory-console-v2.tsx:908-909` | CONFIRMED |
| P1-4 | **PMode Batch 不可 Stop 已送出的 Manager run**；EMode 有 Manager 側 `request_stop` journal | `managed-factory-backend.ts:173-180` vs `programming_batch.py:308-322` | CONFIRMED |
| P1-5 | **C-4 Legacy 直連 Gateway 批次仍可用**，繞過 Route Admission / Job Binding / Receipt v3 | `server.py:109-117` allowlist；`engineering-server-batch.ts`；`server-batch-api.ts` | CONFIRMED |
| P1-6 | `batch-readiness.ts` 被 EMode standalone 與 PMode legacy 共用，但兩者 `readSelected` 語意不同 | `programming-workspace-v2.tsx:322`；`factory-console-v2.tsx:890,898` | CONFIRMED |

### P2（可延後）

| # | Gap | 證據 | 標註 |
|---|---|---|---|
| P2-1 | Repeat 未實作（`repeat` 必須為 1），IC/cycle/fixture 模型不存在 | `programming_batch.py:67-72`；`emode-batch-retry-stop-policy-v1.md:12-14` | CONFIRMED |
| P2-2 | `MAX_BATCHES_RETAINED=32` / `MAX_RUNS_RETAINED=64` / `MAX_STARTS_RETAINED=256`，多 PPU 量產下保留量不足 | `programming_batch.py:57`；`programming.py:78,85` | CONFIRMED |
| P2-3 | 只有 2 條 Route、僅 Site 2、僅 STM32F103C8T6 | `data/opf/programming-routes/` | CONFIRMED |
| P2-4 | `_view()` 的 counts 固定「一個 Batch 一顆 IC」，多 Site 後必須改 | `programming_batch.py:217-227` | CONFIRMED |

### 併發評估

| 層級 | 現況 | 證據 | 標註 |
|---|---|---|---|
| 單 Site | 已驗證（Site 2 HIL，歷史） | PR #1286 / #1287 紀錄 | CONFIRMED（歷史） |
| 單 PPU 多 Site 並行 | **未實作**：Manager per-alias 一次一 run | `programming.py:378-382`；`programming_batch.py:252-255` | CONFIRMED |
| 多 PPU 並行 | **未實作**：PMode 瀏覽器全域循序 | `managed-factory-backend.ts:9-10,211-212` | CONFIRMED |
| PPU Runtime 能力 | 同一 lease owner **可**並行多 Site；`max_concurrent_jobs` 預設 2（`plasma.yaml:11`），上限 `max_supported_sites`=8 | `site_manager.py:39-40,79,204-233`；`plasma_core/config.py:21,98-101` | CONFIRMED |
| FPGA / SWD 共用硬體序列化 | 程式碼中**找不到**跨 Site 的全域硬體互斥；`OpenOCDInterface` 每 Site 一實例 | `plasma_interfaces/openocd.py:36-52` | CONFIRMED |
| 八通道並行資格 | **未驗證** — 文件明確要求先量測 bounded starvation/latency 才能宣稱 | `fixed-fpga-hardware-broker-eight-site-gate1.md:37`；`manager-optional-control-plane.md:315` | NOT_VERIFIED |

**建議：Gate 1 明文凍結「先保持循序」**，Target Set 支援多 Site 只改 **排程資料結構**，不改執行併發度。

---

## F. PR #1406 重疊分析

PR #1406「Recover standalone EMode Read on current main」逐檔比對：

| 檔案 | #1406 內容 | 與新架構關係 | 標註 |
|---|---|---|---|
| `.codegraphignore` | 新增（7 行） | 無關，可重用 | CONFIRMED |
| `.github/workflows/web-tests.yml` | Playwright timeout 10→15 min | 無關，**新架構需要它** | CONFIRMED |
| `AGENTS.md` | 新增 CodeGraph 區塊 | 無關，可重用 | CONFIRMED |
| `software/web/app/batch-readiness.ts` | `no-op` 文案移除 "Read" | ⚠️ **潛在衝突**：此檔同時被 PMode legacy 消費（`factory-console-v2.tsx:890`），而 PMode legacy 的 batch **仍允許 read**（`:898`），文案與行為不一致 | CONFIRMED |
| `software/web/app/engineering/programming-workspace-v2.tsx` | `operationOrder` 去掉 `read`；新增 per-Site `R` 按鈕；`readSelected: false`；表頭 `(E/P/V)` | ⚠️ **高衝突面**：PR-C/PR-D 都會動此檔（mode 分派點 `:236`）。但 #1406 只動 `StandaloneProgrammingWorkspace`（`:308-1180`），不碰 managed 分支 | CONFIRMED |
| `software/web/e2e/tests/engineering-programming-v2.spec.ts` | +19：Read Memory 獨立 Job 測試 | 可重用 | CONFIRMED |
| `software/web/e2e/tests/epvr-guard.spec.ts` | read checkbox → per-Site 按鈕 | 可重用 | CONFIRMED |
| `software/web/e2e/tests/mock-cd-runtime.spec.ts` | 拆 `perSiteOperationOrder` / `batchOperationOrder` | 可重用 | CONFIRMED |
| `software/web/e2e/tests/mode-workspace-persistence.spec.ts` | read→verify | 可重用 | CONFIRMED |
| `software/web/e2e/tests/pmod-emode-theme-regression.spec.ts` | read→verify | 可重用 | CONFIRMED |
| `software/web/e2e/tests/programming-job-test-helpers.ts` | `expectedOperationsByMode = { engineering:[E,P,V], production:[E,P,V,R] }` | ⚠️ **直接衝突**：若 PR-D 讓 PMode 也移除 batch read，`production` 那行必須同步改 | CONFIRMED |
| `software/web/tests/engineering-programming-v2-contract.test.mjs` | +14：source-level 契約斷言（正則比對原始碼字面） | ⚠️ **脆弱**：PR-C 任何格式變動都會打破 | CONFIRMED |
| `software/web/tests/programming-job-control-design-system-contract.test.mjs` | 斷言 `engineering:` / `production:` 兩行 | 與 helpers 連動 | CONFIRMED |
| `software/web/tests/source-integration.test.mjs` | 斷言 `operationOrder` 與 `Read Memory` aria-label | 同上 | CONFIRMED |

**重疊結論：**

- **可完全重用（不得重做）**：`.codegraphignore`、`AGENTS.md` CodeGraph 區塊、CI timeout、6 個 e2e spec 的 Read 行為修正。
- **必須以 #1406 為基礎往上疊（不得覆寫）**：`programming-workspace-v2.tsx` 的 `StandaloneProgrammingWorkspace` 區段、`programming-job-test-helpers.ts`。
- **建議執行順序**：**先讓 #1406 通過 Gate 2 併入 main，再開 PR-A**。
  否則 PR-C/PR-D 與 #1406 會在同三個檔案產生難解的手動 conflict。
- **#1406 CI 狀態**：PR body 自述 lint PASS / `npm test` 286/286 / 6 個 Playwright PASS，
  但註明「CI for the final HEAD is pending」。本次未重跑。**NOT_VERIFIED**

---

## G. PR 切分與執行順序

### 前置：PR #1406 先合併（Gate 2）

> 不是本次 Gate 1 的產出，但是 PR-C / PR-D 的硬相依。

### PR-A — Architecture Contract / ADR（無程式碼）

| 項目 | 內容 |
|---|---|
| 相依 | 無（可立即開始） |
| 修改檔案 | 新增 `docs/architecture/unified-programming-architecture-v1.md`；更新 `emode-batch-retry-stop-policy-v1.md`（多 Site）、`pmode-factory-console-v2.md`（Manager-owned Batch）、`docs/development/plasma-manager.md`、`docs/development/plasma-web.md` |
| 正向測試 | 文件 lint / 連結檢查 |
| 負向測試 | N/A |
| 驗收條件 | 明文凍結：① Target Set schema；② EMode=單 PPU 多 Site / PMode=多 PPU 多 Site；③ **flash_cycle 保留為 legacy，不移除**；④ 併發維持循序；⑤ OUTCOME_UNKNOWN 不自動重送；⑥ Read 永不入 Batch；⑦ Resource Set 變更策略 |
| Gate 2 Readiness | 文件 only，CI 綠即可 |

### PR-B — Shared Manager Batch Orchestrator（後端）

| 項目 | 內容 |
|---|---|
| 相依 | PR-A |
| 修改檔案 | `plasma_manager/programming_batch.py`（`site_id` → `targets[]`、`parse_policy` threshold 解除、`_run_attempts` 走訪 Target Set、`_view` counts 改 per-Site、`_close_interrupted` 逐 Site 判定）、`plasma_manager/programming.py`（`_active_run` / `retry_block` 保持 per-alias、`issue_batch_start` 記錄 targets）、`plasma_manager/bootstrap_server.py`（路由不變） |
| 正向測試 | `tests/test_programming_batch_coordinator.py` 擴充：單 PPU 多 Site、多 PPU 多 Site、每 Site 各自 plan/run/Job、per-Site receipt 聚合、stop queuing 跨 Site、journal 重啟復原逐 Site 判定 |
| 負向測試 | ① 某 Site Route 不存在 → 該 Site BLOCKED，其他 Site 繼續；② 某 PPU OUTCOME_UNKNOWN → 該 PPU 後續 Site 全停、其他 PPU 繼續；③ `repeat != 1` → 400；④ `retry_limit > 5` → 400；⑤ 重複 `start_id` → 409；⑥ Manager 重啟 → 絕不重送 |
| 驗收條件 | Host-only pytest 全綠；`auto_retry=DISABLED` 不變；SAFE_OFF 檢查不變；journal fsync 不變 |
| Gate 2 Readiness | Host-only；**HIL NOT_RUN** |

### PR-C — EMode Multi-Site（前端）

| 項目 | 內容 |
|---|---|
| 相依 | PR-B + **PR #1406 已合併** |
| 修改檔案 | `app/engineering/managed-programming-workspace.tsx`（`chosenSiteId` → `selectedSiteIds`、Batch targets、per-Site 列狀態）、`app/programming/managed-programming.ts`（`ManagedBatchRequest` 加 `siteIds`）、`app/engineering/bundle-programming-api.ts`（`BatchInput` 加 `targets`） |
| 正向測試 | 新增 `software/web/tests/emode-multi-site-contract.test.mjs`；e2e `emode-managed-programming.spec.ts` 擴充多 Site |
| 負向測試 | ① 選到未宣告該 ICPN 的 Site → Start disabled 且顯示 Route 原因；② 任一 Site 不 programmable → 整個 Start 封鎖；③ OUTCOME_UNKNOWN hold 存在時 Start disabled；④ Read Memory 仍為 per-Site 獨立 Job |
| 驗收條件 | EMode 仍限制單 PPU（UI + Manager 雙重）；Read 不入 Batch；`npm test` 全綠 |
| Gate 2 Readiness | Host-only + Playwright；HIL NOT_RUN |

### PR-D — PMode Shared Programming Engine（前端 + 後端對接）

| 項目 | 內容 |
|---|---|
| 相依 | PR-B、PR-C |
| 修改檔案 | `app/fleet/managed-factory-backend.ts`（`ManagedProductionBatch` → 改為 Manager Batch 的觀測器）、`app/fleet/factory-console-v2.tsx`（`:680-682` 逐 PPU 載 Route；`:909` 不再只濾 Image Operation；新增 Start hold / reconcile UI）、`app/programming/managed-programming.ts`（共用） |
| 正向測試 | `pmode-production-admission-contract.test.mjs` 擴充；新增 `pmode-manager-owned-batch-contract.test.mjs`；e2e `pmode-managed-programming.spec.ts` |
| 負向測試 | ① PPU-A 有 Route、PPU-B 無 → 只有 B 的 Site 被封鎖（驗 P0-6 已修）；② 重新整理頁面 → Batch 仍可從 Manager 還原；③ Batch 回應遺失 → 顯示 Start hold，可 reconcile/void，**不得**自動重送；④ 某 PPU OUTCOME_UNKNOWN → 只 latch 該 PPU |
| 驗收條件 | **flash_cycle 路徑保持可用且不變**；PMode 新增 `operations[]` 為可選；Resource Set 切換的 B1/B2/B3 行為在 UI 明示 |
| Gate 2 Readiness | Host-only；**Site 2 HIL 為後續獨立 Gate** |

### PR-E — Host-only Tests / E2E

| 項目 | 內容 |
|---|---|
| 相依 | PR-B、PR-C、PR-D |
| 修改檔案 | `tests/test_programming_batch_coordinator.py`、`test_programming_start_reconciliation.py`、`test_manager_bundle_programming_rest.py`；`software/web/tests/*`；`software/web/e2e/tests/*`；`programming-job-test-helpers.ts`（與 #1406 的 `expectedOperationsByMode` 對齊） |
| 正向測試 | 跨 Mode 單一 Engine 的 source-level 契約（擴充 `unified-managed-programming-contract.test.mjs`） |
| 負向測試 | ① EMode 不得出現 `flash_cycle`（現有 `unified-managed-programming-contract.test.mjs:85`）；② 任何路徑不得出現 auto-resubmit；③ Read 不得出現在 Batch operations |
| 驗收條件 | `npm test` + `pytest` + Playwright 全綠；CI 15 分鐘上限（來自 #1406）足夠 |
| Gate 2 Readiness | 完整 CI 綠；HIL 仍為獨立 Gate |

**執行順序**：`#1406 (Gate 2)` → `PR-A` → `PR-B` → `PR-C` → `PR-D` → `PR-E`。
PR-C 與 PR-D 不可平行（共用 `managed-programming.ts`）。

---

## H. 風險、阻塞項與未決決策

| # | 項目 | 說明 | 標註 |
|---|---|---|---|
| R-1 | **Resource Set 切換風險（最高）** | PMode 從 `flash_cycle` Route 改到 `-operations` Route 會改變 `resource_set_sha256`，使現場每台 PPU 第一次 Job 前強制 B1/B2/B3 Activate。量產現場這是可觀的停機 | CONFIRMED |
| R-2 | **OPF Package Provider 只接受 flash_cycle** | `execution_router.py:68` `request.operation is not Operation.FLASH_CYCLE` → `PACKAGE_PROVIDER_NOT_READY` | CONFIRMED |
| R-3 | **三套 Programming 路徑共存** | Manager-owned / Browser-owned / Legacy 直連 Gateway。AGENTS.md:59 的 Replace-by-Default 要求同一次遷移所有 dependents，但 C-4 退場未在本次範圍 | CONFIRMED |
| R-4 | **#1406 的 source-level 正則測試易碎** | `engineering-programming-v2-contract.test.mjs` 以正則比對 `.tsx` 字面 | CONFIRMED |
| R-5 | **八通道並行無實機證據** | 不得在任何文件、UI 或 PR 描述中宣稱支援 | NOT_VERIFIED |
| R-6 | **Z2 Runtime 版本未查證** | Manager 端 `operations[]` 已在 main，但 Z2 上跑的 Runtime 是否支援未驗證 | NOT_VERIFIED |
| R-7 | **只有 Site 2 有 Route** | 多 Site 功能在現場只有 1 個可用 Site，Host-only 測試需用 fixture Route | CONFIRMED |

**未決決策（需 owner 裁示）：**

1. **D-1**：PMode 是否改用 `operations[]`？或維持 `flash_cycle` 直到 HIL 通過？
   （建議：維持 legacy，PR-D 只加能力不切換預設）
2. **D-2**：Legacy 直連 Gateway 批次（C-4）是否在本次一併退場？（建議：不，另開 Gate 1）
3. **D-3**：PMode Retry 是否開放（目前固定 0）？若開放，`failedSiteStopThreshold`
   要改為統一的 `stop_policy` 物件嗎？
4. **D-4**：EMode Batch 是否應允許「不同 Site 用不同 ICPN / 不同 Image」？
   （目前一個 Batch 一組 plan_body）
5. **D-5**：Stop Policy 的 `threshold` 上限（目前硬限 1）在多 Site 後的預設值？
6. **D-6**：`MAX_BATCHES_RETAINED=32` 等保留量是否要提高？

**本次稽核未違反的既有凍結：**

- 未新增任何 blocking gate。
- 未修改 `flash_cycle` legacy 路徑。
- 未在共用 checkout 做任何 checkout/switch。

---

## I. Gate 1 驗收標準

| # | 標準 | 狀態 |
|---|---|---|
| 1 | 確認 origin/main 與 PR #1406 的實際 HEAD SHA | 完成（§0） |
| 2 | 產出 EMode/PMode 完整 Call Graph | 完成（§C，含第三條 Legacy 路徑） |
| 3 | 提出統一 `(PPU Alias, Site ID)` Target Set 與兩 Mode 的 scope 約束 | 完成（§D-1） |
| 4 | Operations 模型統一方案 + 移除 flash_cycle 的影響分析 | 完成（§D-2，結論：不移除） |
| 5 | Manager-owned vs Browser-owned Batch 比較 + 持久化/Identity/排程/恢復/Stop/Idempotency 設計 | 完成（§B、§D-3） |
| 6 | Batch Policy 比較與統一安全契約；OUTCOME_UNKNOWN 不自動重送 | 完成（§D-4，5 條不可協商契約） |
| 7 | 核對 PMode 是否用第一台 PPU 的 Route 作全域資格 | 完成：**確認屬實（UI 層）**，執行層已逐 PPU（§E P0-6） |
| 8 | 併發分級評估；不得宣稱八通道並行 | 完成（§E 併發評估，標註 NOT_VERIFIED） |
| 9 | Receipt/Recovery 統一方案 | 完成（§D-6） |
| 10 | PR #1406 逐檔重疊分析，不得覆寫 | 完成（§F，14 檔逐檔） |
| 11 | PR-A～PR-E 切分，各含相依/檔案/正負向測試/驗收/Gate 2 Readiness | 完成（§G） |
| 12 | 全程唯讀，未改檔、未建 PR、未部署、未操作硬體、未動 Dirty Worktree | 確認 |

**進入實作前，owner 需裁示 §H 的 D-1～D-6。** 本稽核未進入實作階段。
