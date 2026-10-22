# PLASMA Path 3 — Repo-first Token Optimization RCA Closure

**狀態：Engineering DONE / 階段性結案。** 原始歸檔已於 [PR #1129](https://github.com/physicslu/plasma/pull/1129) 經 Gate 2 合併至 main；本節新增的 Linux Direct 證據補充另需經本次文件 PR 的 Gate 2。**Token 完整因果歸因沒有結案**，仍以低優先級技術債追蹤。

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

## Linux Codex Direct 9×9 補充樣本（2026-10-23；Owner-reported）

**證據等級：USER_REPORTED / NOT_INDEPENDENTLY_VERIFIED。** 下列兩次新版 Linux Direct 測試的 JSON 數值、Codex CLI 版本、輸出檔 SHA-256 與驗收結果由 Owner 在對話中直接提供。Repo 審查者沒有連線讀取 Linux 工作區中的 JSON、Python 程式、stdout、原始 Codex Session 或模型伺服端計量；因此僅能**獨立重算報告中的算術、核對 Git 上既有 Work Order 與 SHA 格式**，不能把這兩份本機結果提升為已獨立實測的 PASS。保留首次失敗樣本以避免倖存者偏差。

相同的 **`nine-nine-path3` 工作目標** 源自 `specs/engineering-dispatch/development-tasks-v1.json`：`Build a Python 9x9 multiplication-table program for factors 1 through 9`，輸出路徑 `scripts/experiments/plasma_nine_nine_codex_generated.py`。兩次 Direct 都固定 Git HEAD `8239fdf4746fdb9dbc6388a77a399bc055004988`，根目錄 `AGENTS.md` 為 **17,285 bytes**，CLI `codex-cli 0.163.0`；以單次全新 `codex exec --json` 程序執行。**提示不是與 Path 3 逐位元組相同**：Direct 包含額外的隔離工作樹、輸出檔、CPU-only、驗收與安全指示；Attempt #2 另外明確聲明 Owner Gate 1 允許建立單一測試檔案。故「相同案例」不等於「相同 Prompt／Session」。

| Owner 回報 | Attempt #1（失敗樣本） | Attempt #2（成功樣本） |
| --- | --- | --- |
| UTC 執行起訖 | 2026-10-22 17:01:17.088974–17:01:45.863209 | 2026-10-22 17:09:01.140073–17:09:33.250952 |
| Wall Time | 28.774 秒 | 32.111 秒 |
| Codex CLI exit | 0 | 0 |
| Source created | **false**（Git 工作樹後續唯讀檢查為乾淨、預期路徑不存在） | **true** |
| Python program exit | null（未執行） | 0 |
| 9×9 驗收 | **FAIL — 未交付程式；不是乘法運算錯誤的證據** | **81/81 PASS（Owner 本機腳本回報）** |
| Input Tokens（含 Cached） | 95,960 | 138,815 |
| Cached Input Tokens | 79,616 | 123,776 |
| Non-cached Input | 16,344 | 15,039 |
| Output Tokens | 1,493 | 2,239 |
| Usage status | REPORTED | REPORTED |
| Model requested / Effort requested | `gpt-6-sol` / `medium` | `gpt-6-sol` / `medium` |
| Effective Model / Effort | **NOT_VERIFIED** | **NOT_VERIFIED** |
| Per-model request count | **NOT_AVAILABLE** | **NOT_AVAILABLE** |
| Source SHA-256 | null | `00408ded47a40b955e8757b9deba0607398ba4de1547085dfae78087a4480804` |
| Stdout SHA-256 | null | `29889cb9189d5756064bd05eebfc0d46ea0bbbfc6dc0a5cf115825b7d456fe` |

Attempt #2 `stdout_matches_path3_expected = false`：**不等於算術失敗**。原始工作目標允許自行選擇 CSV 欄名與程式實作，因此逐位元組 stdout SHA-256 不必與 Path 3 相同；本機驗證腳本聲稱以 81 個唯一的 `(a,b,a*b)` 驗收。兩個 SHA 僅為 Owner 回報的識別資料，**尚未獨立比對對應原始位元組**。Attempt #1 在失敗時即使 `codex_exit_code=0`，也不能視為 Task PASS。

### 跨執行型態對照：描述性數值，不是受控 A/B

| 測試樣本／證據來源 | Input | Cached Input | Non-cached Input | Output | 功能／計量狀態 |
| --- | ---: | ---: | ---: | ---: | --- |
| 舊版 Linux Direct，歷史既有 Session（Owner 本機 Telemetry） | 1,951,915 | 1,927,680 | 24,235 | 6,339 | 81/81 PASS（Owner-reported；16 unique Response records） |
| **新版 Linux Direct Attempt #1**（Owner JSON） | 95,960 | 79,616 | 16,344 | 1,493 | **FAIL — source not created** |
| **新版 Linux Direct Attempt #2**（Owner JSON） | 138,815 | 123,776 | 15,039 | 2,239 | **81/81 PASS（Owner-reported）** |
| 舊版 SWPC Path 3（GitHub artifact verified） | 251,614 | 192,896 | 58,718 | 2,664 | 81/81 PASS |
| 新版 SWPC Path 3（GitHub artifact verified） | 148,319 | 118,272 | 30,047 | 2,649 | 81/81 PASS |

從舊版 Direct 成功樣本到新版 Direct Attempt #2，**總 Input 觀察到 −92.89%、Cached −93.58%、Non-cached −37.95%、Output −64.68%**；舊版既有 Session 的完整 Turn 邊界約 **126.427 秒**，新版 Attempt #2 的 Codex CLI 單次程序約 **32.111 秒**（量測範圍也不同，不能直接當成等價效能提升）。舊版 Direct 16 次 Response、平均每次約 121,995 Input，而新版 **逐次模型請求數 NOT_AVAILABLE**。新品樣本含 123,776 Cached，比例約 89.17%。Input 已包含 Cached，不可重複加總。

**不得將 −92.89% 歸因於 PR #1128 的 `AGENTS.md` 精簡，也不得宣稱 Fresh Session 必然貢獻了特定百分比。** Fresh Session 減少歷史上下文是重要候選解釋，但仍與 Response 次數、工具／迭代路徑、提示差異、Prompt Cache、有效 Model/Effort、CLI 差異及執行上下文混雜。Path 3 使用 `codex-cli 0.162.1`；新版 Linux Direct 使用 `0.163.0`；舊版 Linux Direct 的精確 CLI 版本沒有獨立證據。新版 Direct 的 `gpt-6-sol`／`medium` 是**要求設定**而不是可證實的**生效設定**。只有配對控制條件、來源可驗的 Fresh Session A/B，才能估算各因素貢獻。

**證據保留界線：**Owner 本機數值摘要（Attempt #1 與 #2）應由 Owner 留存；不要把私有 rollout JSONL、原始 Session、Prompt、憑證或任意本機工作目錄上傳 Repository。本節是提供的脫敏計量及驗收結果歸檔，無新的 SWPC／Codex Run／硬體操作。此補充不重新開啟先前已合併的 Path 3 優化結案；Per-response Token Attribution 保留原低優先級 TODO。

## RCA / 結案決策

- **VERIFIED — 重複大型上下文的 Input 計量放大機制：**在獨立 Linux Codex Direct 16-response 樣本中，1,951,915 Input 含 1,927,680 Cached。這是可觀測的 Token 計量特徵；**並不證明 SWPC Path 3 的模型呼叫次數同為 16**。
- **VERIFIED — 既有 Repository 指令體積偏大：**PR #1128 前根目錄 `AGENTS.md` 為 62,093 bytes，超過預設的 32 KiB 專案指令預算；精簡版 17,285 bytes，完整詳細規範已另存。
- **VERIFIED — 兩次真實 Path 3 觀察差異：**同一測試任務下，新版總 Input 下降 41.05%、non-cached Input 下降 48.83%，功能 81/81 維持 PASS。
- **NOT_VERIFIED — 41.05% 的完整因果歸因：**尚未排除模型／Effort、既有 Context、Prompt Cache 與模型／工具迭代差異。不可對外宣稱「PR #1128 單獨造成節省 41.05%」，也不可據此推算真實金額或用量配額。
- **NOT_AVAILABLE — 每次 Response 的模型請求計量：**標準 `codex exec --json` Turn 事件沒有足夠的逐請求／實際載入來源歸因資料；不得用 `item.completed` 數量當作模型請求數。
- **NOT_RUN — 實際指令載入內容與長期重複樣本 A/B：**當前不阻擋既有 Token 優化的階段性結案。

**結案範圍：**`Repo-first Token Optimization = DONE`（PR #1128 merge + 兩組真實 SWPC CPU-only 驗證 + 證據歸檔），不代表此文件 PR 可以跳過 Gate 2。**殘餘工作：**`Per-response Token Attribution = TODO / LOW`，見 [Development Debt Register](todo.md)。只有在未來真實工程任務又出現成本或上下文異常時，才優先評估是否需要新的受保護、純數值 telemetry；不要因本結案新增 SWPC Runner、Dispatcher、監測 Agent 或讀取原始 Session。
