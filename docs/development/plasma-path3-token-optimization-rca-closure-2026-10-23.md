# PLASMA Path 3 — Repo-first Token Optimization RCA Closure

**狀態：Engineering DONE / 階段性結案。** 此文件為 Gate 1 的證據歸檔變更，必須經獨立 Gate 2 合併才能成為正式 main 文件。**Token 完整因果歸因沒有結案**，另以低優先級技術債追蹤。

**範圍：** 原有 PLASMA Development Mode Path 3、CPU-only `nine-nine-path3` 任務、GitHub Actions + `SWPC-plasma-codex` Runner。此報告歸檔既有執行證據；**沒有新增執行、重跑 Codex、部署或操作 Z2、DUT、FPGA、電源、USB。**

## 修復與 Source Pin

- 修復 PR：[**#1128 Repo-first Path 3 context optimization**](https://github.com/physicslu/plasma/pull/1128)，2026-10-22 已用 Merge Commit 合併。
- Merge SHA：`8239fdf4746fdb9dbc6388a77a399bc055004988`。
- Merge Parents（順序）：`b3caa1d289f375125f781f2a563fe1eb8b02204e`（原 main）、`f11d9496f9bd17910437e3f480144a8128802e81`（PR #1128 exact HEAD）。
- Merge Git Tree = PR HEAD Git Tree：`ee1091e3ab4ea798bf44cfe3bff50a5b0cfaacee`。
- 變更摘要：根目錄 `AGENTS.md` 從 **62,093 bytes** 精簡至 **17,285 bytes**（減少 44,808 bytes，約 **72.16%**）；完整條款移至 `docs/development/plasma-autonomous-development-contract-full.md` 並保持規範效力；縮短通用 Path 3 指令；既有 Dispatcher、Owner Work Order、Sandbox、Runner 和權限邊界不變；新增純數值 `codex_context_audit`。

## 同任務、兩次真實 SWPC Path 3 Run

| 欄位 | 修復前：baseline | 修復後：validation |
| --- | --- | --- |
| GitHub Actions Run | [#39768663770](https://github.com/physicslu/plasma/actions/runs/39768663770) | [#39808595675](https://github.com/physicslu/plasma/actions/runs/39808595675) |
| GitHub issue / Task | #981 / `nine-nine-path3` | #981 / `nine-nine-path3` |
| Pinned / trusted commit | `b570fe4831e80212924994bedbb2969e12a1f01f` | `8239fdf4746fdb9dbc6388a77a399bc055004988` |
| Task Registry SHA-256（Receipt） | `10506abbd5578083e0136514cae05ac33b218f32b32bfa178ca3e599763ba55c` | 同左 |
| Git Task Registry blob | `09ce12eedd983d2f514202a007faa64af8254c22` | 同左 |
| Runner / Codex CLI | `SWPC-plasma-codex` / `0.162.1` | 同左 |
| Github Run 結果 | SUCCESS；Codex exit 0 | SUCCESS；Codex exit 0 |
| 9×9 正確性 | **81/81 PASS** | **81/81 PASS** |
| Code output SHA-256 | `142d9b788a5902e98048690e75e9d91ac8e22334c592f7e2e5a93e8bc878bc5d` | 同左 |
| 完整 Workflow wall time | 104 秒（11:11:05–11:12:49 UTC） | 105 秒（15:50:33–15:52:18 UTC） |
| Codex Job 內執行步驟 | 72 秒（11:11:28–11:12:40 UTC） | 76 秒（15:50:52–15:52:08 UTC） |
| Model / Reasoning Effort | **NOT_VERIFIED** | **NOT_AVAILABLE**（Receipt 無有效值） |

相同的 Task Registry blob 證明 **Work Order 的客觀任務定義沒有改變**；但不能推論模型、Effort、Cache warm-up、Tool 行為及所有其他上下文均相同。兩次 Artifact 內的 CSV 均已重新獨立解析驗證：表頭與 81 個唯一因數對 `(1..9, 1..9)` 均完整，所有乘積正確，且原始輸出的 SHA-256 一致。**81/81 PASS 是 CPU-only 功能正確性，不是硬體或真實燒錄驗收。**

## Token Usage（Codex CLI `exec --json` 的單 Turn 計量）

| 指標 | 修復前 | 修復後 | 差異 | 變化 |
| --- | ---: | ---: | ---: | ---: |
| Input Tokens（含 Cached） | 251,614 | 148,319 | −103,295 | **−41.05%** |
| Cached Input Tokens | 192,896 | 118,272 | −74,624 | **−38.69%** |
| Non-cached Input（Input − Cached） | 58,718 | 30,047 | −28,671 | **−48.83%** |
| Output Tokens | 2,664 | 2,649 | −15 | **−0.56%** |
| Cached / Input | 76.66% | 79.74% | +3.08 percentage points | — |

**驗證口徑：**輸入計數已包含 Cached Input，不可重複加總。數據是整個 Codex exec 的 `turn.completed` usage，不是逐 Response 計量。非快取 Input 和百分比為本報告按 Receipt 數值直接計算。**執行時間沒有改善**：Workflow 多 1 秒，Codex 工作步驟多 4 秒。

新版 Receipt 還證實：
- `codex_context_audit.repo_root_agents_bytes = 17285`；
- `codex_context_audit.dispatched_prompt_bytes = 1517`；
- `codex_context_audit.actual_instruction_load_status = NOT_VERIFIED`；
- `codex_context_audit.model_request_count = null`、`model_request_count_status = NOT_AVAILABLE`。

前兩項是**檔案與派工字串大小**，不是「模型實際載入的 AGENTS Token」或「模型請求數」。歷史的 Direct Linux Codex 16 Responses／1,951,915 Input 屬另一執行型態，參見 [Codex benchmark usage](codex-benchmark-usage.md)，**不得加入這組 SWPC Path 3 A/B 的分母或假稱相同條件。**

## 證據索引與完整性

證據封存於原始 GitHub Actions Artifact，Repository 僅保留固定可核對的 Run ID、原始 Git SHA、SHA-256 與結論，不提交敏感 Session、原始 Prompt、Token 或憑證。GitHub Artifact 有保留期限；過期時可保留此文件的已驗證事實與 Hash，但不能假稱原始檔仍可下載。

| 證據 SHA-256 | 修復前 Run #39768663770 | 修復後 Run #39808595675 |
| --- | --- | --- |
| Artifact ZIP / GitHub digest | `1642a06c375b61a2d5ecd5539927d1699e29aaea6536033034f19e077d0a3ec1` | `9c280169da78e1b9d8695b3a9d1f09532e26ce46218d42a172378e16ce9c45be` |
| Artifact ID | `12421735939` | `12439965048` |
| `codex-token-usage.json` | `0a05781c5545f7716f9fdd0ddcaeb18a149d6d434830c38be2cbbf55d18f2a1a` | `0e20a5e443437dcdd3f8cc06f2c1674d34467093183b59b51d646378cd5dd20e` |
| `engineering-report.md` | `c50dda187ec8cfcb1440da9663f7ea95634cae20aa407cf8e7cef29dfed3b7a5` | `0ab2e07e62517a7df9a5e69e2e98127944fd9c777c84fb3db26a431d306c0316` |
| Redacted `codex.log` | `5e388e492643f0f7207d0a34daddd5b4ff5115bb24e1802feb8d122e2b5cc779` | `f8a30e7ca8286f726f15db9ed8e3ab7544a86377489dd3b2fc95835f58bf543c` |
| Generated source | `93d3aed9688c6c435f028996eb2fbd30e6b2f62ac1d026da36d817ec6585dd4d` | `fde9caf82113c7666652207c36a74e9c5ea0e9cf9268d0f54cfaf280f3477184` |

校驗方法：以 GitHub Artifact ID 下載 ZIP，先對 ZIP 計算 SHA-256，比對表內 digest；再在壓縮包內查驗 `_temp/plasma-path3-receipt.json` 的欄位、收據 Hash 與 `_temp/plasma-path3-engineering-evidence.tar.gz` 的實際 CSV。已於本次 Gate 1 歸檔前對兩個 ZIP **獨立計算 SHA-256 並逐筆驗算兩份 9×9 CSV**，吻合表格與預期值。

## RCA / 結案決策

- **VERIFIED — 重複大型上下文的 Input 計量放大機制：**在獨立 Linux Codex Direct 16-response 樣本中，1,951,915 Input 含 1,927,680 Cached。這是可觀測的 Token 計量特徵；**並不證明 SWPC Path 3 的模型呼叫次數同為 16**。
- **VERIFIED — 既有 Repository 指令體積偏大：**PR #1128 前根目錄 `AGENTS.md` 為 62,093 bytes，超過預設的 32 KiB 專案指令預算；精簡版 17,285 bytes，完整詳細規範已另存。
- **VERIFIED — 兩次真實 Path 3 觀察差異：**同一測試任務下，新版總 Input 下降 41.05%、non-cached Input 下降 48.83%，功能 81/81 維持 PASS。
- **NOT_VERIFIED — 41.05% 的完整因果歸因：**尚未排除模型／Effort、既有 Context、Prompt Cache 與模型／工具迭代差異。不可對外宣稱「PR #1128 單獨造成節省 41.05%」，也不可據此推算真實金額或用量配額。
- **NOT_AVAILABLE — 每次 Response 的模型請求計量：**標準 `codex exec --json` Turn 事件沒有足夠的逐請求／實際載入來源歸因資料；不得用 `item.completed` 數量當作模型請求數。
- **NOT_RUN — 實際指令載入內容與長期重複樣本 A/B：**當前不阻擋既有 Token 優化的階段性結案。

**結案範圍：**`Repo-first Token Optimization = DONE`（PR #1128 merge + 兩組真實 SWPC CPU-only 驗證 + 證據歸檔），不代表此文件 PR 可以跳過 Gate 2。**殘餘工作：**`Per-response Token Attribution = TODO / LOW`，見 [Development Debt Register](todo.md)。只有在未來真實工程任務又出現成本或上下文異常時，才優先評估是否需要新的受保護、純數值 telemetry；不要因本結案新增 SWPC Runner、Dispatcher、監測 Agent 或讀取原始 Session。
