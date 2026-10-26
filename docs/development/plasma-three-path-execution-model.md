# PLASMA — Three-Path Work Execution Model（三路徑工作執行模型）

> **狀態：PLASMA Development Mode 三路徑規範；正式治理條款同步定義於根目錄 AGENTS.md。**
>
> **範圍：開發、CI、SWPC 工程工作調度，不是產品 PPU 的八 Site 燒錄排程器。**
>
> **注意：這份文件定義路徑與授權，不代表已部署通用 Dispatcher、觸發任何 Codex Job 或完成硬體驗收。**

本文件與根目錄 [AGENTS.md](../../AGENTS.md) §11.1～11.1B 同步。**截至 2026-10-25（PR #1159、#1160 已合併），Path 2／3 的實際 Development Mode 入口為 Issue #981 `issue_comment` → 可信 `main` Dispatcher → SWPC Runner；另外的 `workflow_dispatch` Qualification Runtime 仍停用。** 實際 GitHub Workflow、Linux 權限與裝置狀態高於歷史文字敘述，不得把授權、程式修改或 CI PASS 說成硬體 PASS。

## 一、第一性原理：用執行邊界，而不是 UI 介面分類

- **ChatGPT Chat** 與 **ChatGPT Work Mode** 都可作為三條 Path 的互動入口；「Work」的工作能力不等同於必須打開「Work Mode」。
- **GitHub Actions** 是 Trigger／受控執行與驗證平台，GitHub-hosted 與 SWPC self-hosted Runner 是不同信任／存取邊界。
- **CLI 與 Codex 不同**：CLI 執行事先固定的指令；Codex 在核准的工作契約內自主修改、測試、迭代。不能把 Codex 存在視為可以任意存取硬體。
- **CI 不等於 CD**：合併 PR 不自動授權部署、重啟、改 FPGA、DUT 電源或燒錄 IC。部署、Runtime 和硬體行為必須明列 Gate 1 授權範圍。
- **Gate 1 選 Path 是授權與執行計畫的一部分**，不是第三個 Gate。
- **Gate 1 必須完成已授權的開發與真實驗收**：Path 2/3 若要求 SWPC 實測，應在合併前取得 Runner 執行證據並由 ChatGPT 判定；失敗在原 Gate 1 內修正、重測。
- **Owner 批准新增機制**：優先沿用已驗證的建置腳本、Board Files 準備、Dispatcher、Runner 及 Artifact 檢查。既有 Gate 1 內的缺陷修復與重測不需重複批准；但若需要新腳本、Workflow、Runner、驗證架構、隔離平台或新增獨立機制，先提出證據、既有方案不可重用的原因、最小修改範圍與影響，取得 Owner 明確同意再實作。不得將額外設計工作偽裝成已核准的例行修補。
- **Evidence Reuse / Execute-first**：已有同一工具鏈、板卡版號、Runner 與適用契約的真實有效證據時，不再新增第二套 preflight、Workflow、Runner 或重複要求 Owner 批准；已批准的任務應直接執行既有受控 Path，失敗才依 Exit Code／實際 Receipt 在同一 Gate 1 修補。仍保留當次執行所必須的身分、SHA、權限、硬體隔離及範圍保護，不得因省略重複確認而繞過安全控制；缺少執行證據須標示 NOT_RUN。
- **Gate 2 只批准特定 PR Merge**：不得為了觸發可信 `main` Dispatcher，先合併尚未完成真實驗收的開發內容；現行 Development Dispatcher 已支援綁定未合併 PR 精確 HEAD。Post-merge release/deployment 的獨立操作按原 Gate 1 明示範圍處理，不取代開發階段 E2E。


## 二、Path 1 — ChatGPT Direct Work

**推薦場景：** 程式碼、文件、資料研究、OpenOCD catalog、Host-only Build／Unit Test／Contracts 等不需要 SWPC 真實環境的工作。

```mermaid
flowchart TD
  A["Gate 1｜使用者批准 Path 1、工作計畫和範圍"]
  B["ChatGPT Direct Work｜Chat 或 Work Mode"]
  C["GitHub Branch／Pull Request"]
  D["GitHub-hosted CI｜Build／Unit Tests／Contracts／Evidence"]
  E{"全部相關驗證 PASS？"}
  F["ChatGPT 在授權範圍內修正 PR"]
  G["PR Ready｜Gate 2 使用者審查 HEAD／CI／Rulesets／Threads"]
  H["Merge to main｜核實 Merge SHA 與 Parents"]
  A --> B --> C --> D --> E
  E -- "否" --> F --> D
  E -- "是" --> G --> H
```

**執行者：** ChatGPT 透過可用的 repository 工作能力實作及管理 PR；GitHub-hosted Runner 執行適用 CI。不得因工作源於聊天而誤標為 SWPC 或 Work Mode 的遠端執行。

## 三、Path 2 — SWPC CLI Work

**推薦場景：** 需要 SWPC 環境／測試設備，而固定 Bash／Python／Linux 工具即可完成的可重現工程工作，例如特定編譯、現場唯讀盤點、受控 HIL 或測試資料收集。

```mermaid
flowchart TD
  A["Gate 1｜使用者批准 Path 2 固定 CLI 與驗收條件"]
  B["開發分支及受控 Work Order｜綁定核准來源 SHA"]
  C["GitHub Actions｜實際觸發共用 Dispatcher"]
  D["既有 SWPC-plasma-codex Runner｜執行固定 CLI"]
  E["蒐集真實 Exit Code／Output／Run ID／Evidence"]
  F{"Gate 1 真實驗收 PASS？"}
  G["同一 Gate 1 修改、重新執行並取得證據"]
  H{"有需要合併的程式變更？"}
  I["PR Ready + CI｜Gate 2 只批准 Merge"]
  J["完成報告｜無 PR 不需要 Gate 2"]
  A --> B --> C --> D --> E --> F
  F -- "否" --> G --> C
  F -- "是" --> H
  H -- "是" --> I
  H -- "否" --> J
```

**執行者：** SWPC Runner 執行已審查的固定 CLI 命令；不是讓 Codex 推理與改碼。CLI 任務不可偷偷轉為 Path 3。沒有符合 Gate 1 條件的已啟用 Trigger／Runner 時，必須回報 `NOT_RUN` 和具體阻礙，不能把批准訊息當作 GitHub Job 已經啟動。

**Path 2 動態 CPU-only Work Order（已合併 PR #1163）：** 使用既有 `plasma.development.work_order.v1`，`execution_path: path2-cli`、`capability: cpu-only`，並指定既有 `scripts/experiments/<name>.py` 與 `argv`。省略 `scope` 時視為 `host-only`；明示時只能是 `host-only`。預設 `verification: stdout-sha256`，要求合法的 `expected_stdout_sha256` 並核對 Exit Code 0；明示 `verification: exit-code` 時不得提供 `expected_stdout_sha256`，仍保留實際 Stdout、Stderr、Exit Code 及觀測的 Stdout SHA256，且 **Exit Code 0 不代表功能或硬體驗收 PASS**。動態 CPU-only `timeout_seconds` 預設 120 秒、允許 1–180 秒；`argv` 最多 16 個、每個最長 256 字元，保留安全字元／路徑檢查。Stdout 依 UTF-8 解碼。原 Registry 固定任務仍使用既有 SHA-only 驗證與 40 秒預設值；CPU-only 一律保留 Bubblewrap、Worker Admission 及無裝置／網路命名空間，**本階段不增加任何硬體權限**。

**Path 2 動態 Vivado Host Build（已合併 PR #1164）：** 在既有 `plasma.development.work_order.v1` 中使用 `execution_path: path2-cli`、`capability: vivado-host-build`，提供 `objective`、`acceptance`、`project: pl/projects/z2-fixed-unified-site1`、`toolchain: "2026.1"`、40 位 `board_repo_sha`；`scope` 可省略，或明示為 `host-only`。可依原有契約以 `pr_number`／`source_sha` 指定 Owner 核准的精確 PR HEAD。既有可信 Dispatcher 驗證 Work Order SHA／Worker Admission 後，把建置參數投影給**同一套既有 Site 1 Vivado Host Build Engine**；Toolchain、Board Files SHA、來源、License、Synthesis、Implementation、Timing、DRC 與 BIT／HWH Qualification 仍走原本檢查。沒有 `script`／`argv`／`stage`，不得指定任意 Project 或自動 Download；這項支援不新增 Root／FPGA／MMIO／DUT 權限，也不需要新 Task Registry ID、Workflow 或 Runner。GitHub-hosted CI 只驗證程式契約；不代表 SWPC 實際 Vivado Build PASS。

**Path 2 直接受保護的 Z2 Root 操作（PR #1167 已合併；Issue #1168 已實機驗收 PASS）：** 使用現有可信 Dispatcher、Work Order SHA、SWPC Runner、SSH／sudo 與 Z2 Protected Root Entry，採用 `capability: z2-root-operation`、`scope: guarded-hardware` 及單一 `operation: download|test|restore`。不接受 `stage`／`project`／Profile／自由腳本，不需要舊固定 Task ID 或 Stage Orchestrator；不存在隱含 Full HIL 自動串接。Root Entry 的直接介面僅接受 `operation + source_sha`，驗證 root-owned Git commit pin 與來源 SHA256 Manifest，再由受保護 `pl.hil.fpga_image_root` 實作及 Guard/Admission 檢查 B1／B2／B3、當前 Image、Lock、Golden Restore。**2026-10-25 已完成兩種不同證據：操作員 SSH 一鍵 F1-B Download／3-read MMIO Test／Golden Restore PASS；其後在 [Issue #1168](https://github.com/physicslu/plasma/issues/1168) 以三個獨立的受信任 Path 2 SWPC Runner→Z2 Root 操作驗收 PASS（[Download](https://github.com/physicslu/plasma/actions/runs/40206257358)、[Test](https://github.com/physicslu/plasma/actions/runs/40206377161)、[Restore](https://github.com/physicslu/plasma/actions/runs/40206484938)）。** 三筆均使用合併後來源 SHA `b807f1ac727209cfe1d09e9d2d31a302039e523a` 與同一 Boot ID。**上述證據只涵蓋 F1-B；尚未完成其他 Programmer IP 的 Root 准入、實際 Blue Pill DPIDR／燒錄，亦非八通道 HIL。** 現有 Fixed ABI SWD 控制器與雙 Site RTL 仍只有 Host／RTL 等級證據，不能直接賦予 Root 執行權限。**後續通用架構改採 AP 管理授權與 FPGA Image/IP/ABI 相容性，PS 驗證可信 Manifest、BIN SHA、Board/FPGA 與 Recovery 後下載，PL 載入後提供 Identity／Build／Capability 校驗。Root 是 Image Deployment/Golden Lifecycle，不是每個 Programmer IP 的燒錄 Handler；正常 IC Job 不重新配置 FPGA。SHA256 只證明內容完整，非獨立授權；PL 暫存器本身亦非密碼學驗證。** 完整資格與界線見 `docs/development/path2-generic-fpga-image-loader.md`。

**Development Mode Z2 SSH／sudo 單一憑證原則：** Path 2 與 Path 3 均使用同一 `plasma-codex` 帳號的 `~/.config/plasma/z2-login-smoke.json`，含 `ssh_host`、`ssh_username`、`ssh_password`，以及僅在 sudo 密碼不同時需要的 `sudo_password`。不得讀取或回退至歷史 `z2-dev-credentials.json`；舊的 SWD-05 專用 Route 檔已不屬於 Path 2／3 SSH 憑證契約；兩條 Path 都不得依賴它。`z2-login-known_hosts` 是供兩條 Path 共用的公開 Host Key Pin，**不是第二份憑證**，仍必須保留。舊有憑證須在比對 Host/身分與 sudo 密碼、完成單一憑證及路徑配置寫入／讀回確認後，才由 SWPC worker 本機安全刪除，衝突則停止。此簡化不移除真實 SSH／sudo 驗證、Trusted Main Dispatcher、Root Entry、來源 SHA、B1/B2/B3 與 Restore 保護。

## 四、Path 3 — SWPC Codex Work

**推薦場景：** 必須使用 SWPC 及 Codex 的自主迭代能力，例如多模組問題定位、修復與反覆測試、真實軟硬體整合開發。

```mermaid
flowchart TD
  A["Gate 1｜批准 Path 3 工作範圍與驗收"]
  B["受控開發分支／SHA → GitHub 共用 Dispatcher"]
  C["既有 SWPC-plasma-codex Runner → Codex CLI"]
  D["Codex 自主開發、執行、自測、修正"]
  E["GitHub 收集 Code／Output／Test Log／Run ID"]
  F["ChatGPT 獨立審查真實 Evidence"]
  G{"Gate 1 驗收 PASS？"}
  H["Codex 在相同 Gate 1 修正／重測"]
  I["完成／更新 PR + 必要 CI"]
  J["Gate 2｜只審核與批准 Merge"]
  K["Merge to main｜不重派相同開發任務"]
  A --> B --> C --> D --> E --> F --> G
  G -- "否" --> H --> C
  G -- "是" --> I --> J --> K
```

**Development Mode 實作修訂（2026-10-20；依已合併 PR #1108 更新）：** Path 3 是 Codex 自主工程執行模式，不再以單一 generated Python／CSV 作為唯一工作成果。Codex 可在已授權的候選工作樹內修改 RTL、Tcl、Python、測試和文件，並在適用的核准範圍內執行 Vivado 2026.1 Synthesis、Implementation、Timing、DRC 和 BIT／HWH 建置，記錄實際錯誤、根因／假設、修正、重測以及 SHA256。原有 480 秒 Codex 子程序上限已移除；Workflow 原 12 分鐘上限改為 360 分鐘的外部故障保護，而非要求設計在數分鐘內完成。既有 Candidate 檔案白名單拒絕改碼的檢查已移除，改保存完整 Git diff、未追蹤來源檔與工程報告，由 Reviewer 判讀真實證據。Host-only Vivado Build 只證明主機端建置，不構成 FPGA 載入或其他實體操作的授權。

**Path 3 不預設 Host-only，也不強制人工分流。** 通用 Path 3 Work Order 不要求事先逐一列出 `hardware_stages`，或因單一 Gate 1 工作的建置、部署、修復、重測而重複人工批准。PR #1160 之後，可信 Dispatcher 只傳遞核准的 Objective、Acceptance 及來源識別；Codex 自行選擇工程方法，**不由 Prompt 強制固定工具、Vivado 步驟或 Root Stage 順序**。

**目前 Work Order 欄位契約（已實作）：** 一般 `execution_path: path3-codex`、`capability: codex-workspace` 的動態工作單**不可提供 `scope` 欄位**，也不要求 `hardware_stages`；授權範圍由 Owner 核准的工作目標及驗收條件界定。唯一的 `session_resume: page-boundary-off-by-one` 特例必須明確帶 `scope: host-only`、指定 `source_sha`，僅供 CPU-only 的兩個 GitHub Jobs 延續實驗；**不是**一般 Path 3 的 Host-only Gate，也不授權 Z2／FPGA／DUT。若新增其他 Work Order Schema 或控制平面能力，才需要審核並更新可信 `main` 的 Dispatcher。

**實際的權限邊界仍存在。** Path 3 使用非 Root Bubblewrap，並保留 GitHub Token 隔離與 Trusted Publisher；普通 USB／TTY 依實際 Linux DAC／ACL 可用。對已核准的 Z2 部署／FPGA Manager／MMIO／SWD／DUT 作業，Codex 可選擇已登錄的 SSH／sudo 路徑及適合的現有工具；**Path 2 的直接 Root 操作沒有 Stage 或 Profile 門檻，Path 3 也不必經過 Path 2 Work Order**。若使用既有 Protected Root Entry，仍須符合實際已安裝版本與來源驗證；不能從 PR 原始碼推定 Z2 已部署。安全要求仍為 B1 授權與可信來源、B2 當前裝置所有權／電壓／Image／Golden Restore、B3 實際結果與失敗停止。權限不足或恢復未知必須回報 `NOT_RUN`／`FAIL`，不能聲稱 PASS。實驗一次完整有效 PASS 即停止，失敗才針對性診斷。

**執行者：** 既有 SWPC `SWPC-plasma-codex` Runner 與 Codex CLI；GitHub Actions 負責派工與收集 Code／Output／Log，Codex 負責自行開發、自行執行、自行測試與修正，**ChatGPT 審閱真實證據並判定 PASS/FAIL**。不要讓 SWPC Dispatcher 額外實作一個驗證 Codex 寫法的 AST/特定輸出格式檢查器。Job `SUCCESS`、Codex 自稱 `PASS`、有 Artifact，均不能直接代替獨立驗收。已知限制：

1. **批准 Gate 1 ≠ GitHub Workflow 自動發生。** ChatGPT／授權工具必須確實呼叫可用 Trigger，並以 GitHub Job 證據核對是否執行。若無法觸發，報告 `NOT_RUN`；不要求已批准事項再重複授權。
2. 現有共用 `plasma-engineering-runtime-dispatch.yml` 提供 **Development Mode owner-only Issue #981 入口**。可信 Dispatcher 仍來自 `main`，但已支援在 Owner 核准後讀取同儲存庫未合併 PR 的精確 HEAD SHA 與候選任務 Registry／工作樹；該路徑適用 Path 2/3。**只有變更可信 Dispatcher／Workflow／Work Order Parser 的執行能力時**，才需先合併該控制平面程式至 `main` 才能生效；一般 Path 3 任務沿用現有動態 Work Order 契約，可直接由 Owner Issue #981 指令指定未合併 PR 的精確 HEAD，**不需要先把任務或候選程式合併進 `main`**。正式 qualification `workflow_dispatch` Runtime 仍停用。
3. Codex 建 PR 時，若使用預設 `GITHUB_TOKEN`，**通常不會觸發新的 `pull_request` workflows**。須確保使用核准的 GitHub App token 或其他受控事件機制，讓必要 CI 真正開始。PR 建立成功不能代替 CI PASS。
4. SWPC Codex 帳號可能已有部分硬體存取權；「軟體專用 Prompt」不是 OS 層隔離。Z2／USB／LA／Power／FPGA／DUT 必須依 Gate 1 和安全契約明確允許才操作。
5. **Gate 1 完成 Path 3 真實 E2E 與證據審查，Gate 2 僅批准 Merge**。合併後的 `main` push 可啟動一般 CI，但**不能重新派發同一項 Codex 開發任務**。

### Path 3 Admission、執行結果與證據收集（現行實作）

**安全檢查數量不等於人工 Gate 數量。** 使用者 Gate 1 一次授權
Codex 在既定工作樹／Objective 內自主進行 Code → Test → Fix → Retest，
不需要因可恢復的軟體編譯失敗再向使用者取得批准；超出工作範圍、
權限不足、實體 FPGA／AXI 安全不明及失敗恢復 UNKNOWN，仍必須立即停止。

- **GitHub-hosted Admission**：確認 Owner、Issue #981、PR 與可信 main SHA、
  Candidate 精確 Commit SHA、Task Registry SHA256 及合法 Path。
- **SWPC Worker Admission**：重用同一個 Python `worker_admission()` 函式
  進行第二信任邊界的獨立 SHA/Registry/Runner/Path 檢查，統一回報
  `WORKER_SOURCE_ADMITTED`；不得省略第二次校驗或將它當成另一道人工 Gate。
- **Codex 自主工程迴圈**：單一 Codex CLI 程序在同一 Job 內自行診斷、
  修改及重跑允許的測試；Dispatcher 不新增 Agent Retry Supervisor，
  不另起 SWPC Job，不因 Exit Code 自動重派硬體指令。
- **失敗證據與退出碼（現行實作）**：`run_codex_task()` 於 Codex 非零退出時保留真實 Exit Code 與日誌，回傳 `CODEX_EXECUTION_FAILED_REVIEW_REQUIRED`，Workflow 判為失敗。若 Codex Exit Code 為 0 但缺少工程報告或舊版三檔輸出，現行實作以 `evidence_complete=false` 作為**審查中繼資料**，Receipt 仍可為 `EVIDENCE_READY_REVIEW_REQUIRED`；這不等於工程或硬體驗收 PASS。Trusted Publisher 另要求成功 Exit Code、指定狀態與精確 PR HEAD。
- **失敗後收集**：共用 Workflow 以 `if: always()` 執行獨立的證據收集步驟，
  保存含已暫存／未暫存變更的 `git diff HEAD --binary`、未追蹤檔清單／
  壓縮檔、工程報告、Codex 日誌、Artifact Hash；不因 `set -e`
  造成初始工作失敗時跳過所有證據。Runner 異常中斷、磁碟／網路故障、
  Job 硬超時仍可能讓資料採集不完整，不能宣稱絕對保證。

**驗證邊界：** 以上 Admission、Receipt 與失敗證據收集已有對應程式及 GitHub Workflow；GitHub-hosted 離線測試驗證的是契約，不等於 SWPC Runner、Codex、Z2 或 DUT 的實際端到端測試。任何未取得實際收據的硬體或 Publisher E2E 結果都必須維持 `NOT_RUN`，不得由 CI PASS 推論。

### Candidate Dispatcher 合併前測試入口（PR #1083）

若 PR 修改的是 `scripts/plasma_development_dispatch.py` **本身**，Issue #981
正式 `issue_comment` 入口仍必須執行可信 `main` Dispatcher，不得透過
`--pr/--sha` 偷換授權程式。既有 `pull_request` 已提供 Branch 測試入口；
在**同一份共用 Workflow** 內增加 `candidate-dispatcher-premerge` GitHub-hosted
Job，分別 Checkout 精確 Base SHA 與 Candidate HEAD SHA，驗證 Git Tree
後執行候選 Dispatcher 的**真實命令列程式**與完全模擬的 Owner Event／PR
Metadata／Codex Stub：

- 正例：`authorize` 與 `execute-codex` CLI 依序通過，檢查三種 SHA
  傳遞、12 筆三角數、Exit Code 與 Receipt。
- 負例：模擬 Codex 非零退出須令 Dispatcher 非零退出且保留失敗證據；
  Registry SHA、Candidate SHA 或 Owner 不符須拒絕，且在啟動 Stub 前停止。
- 無 SWPC/self-hosted Runner，無真 Codex、Vivado、硬體／USB／MMIO。
  Stub 暫時設定的 Runner 環境變數**僅是 GH-hosted 內的測試資料**，
  結果必須標示 `HOSTED_SIMULATION_ONLY`，不可宣稱 SWPC E2E PASS。
- 測試 Job 使用 GitHub-hosted ephemeral Runner、唯讀 repo token、不
  持久化 Git credentials；不新增第二份 Workflow／Runner／Dispatcher，
  不呼叫 Issue #981，亦不影響其他 Path 的正式派工模式。

這條入口能在 Merge 前驗證 **Candidate Dispatcher CLI 控制流程**，
但無法驗證 SWPC 上的真實 OS 身分、實際權限隔離與 Codex 行為。
若要在合併前於 **SWPC 真正執行 Candidate Dispatcher**，仍須有可信
主控建立的 OS 級純軟體 Sandbox（不接觸實體設備）並能由獨立證據
證明隔離，不能直接以 GitHub-hosted 假身分或 Prompt 取代。
未建立這一條安全邊界前，SWPC Candidate E2E = `NOT_RUN`。

**合併前 SWPC 純軟體沙箱測試（候選實作）：**
不用授權候選 Dispatcher 作為控制平面。用已存在的可信 main Path 2
`cpu-only` 派工，限定新登錄的
`candidate-dispatcher-premerge-sandbox` 任務，從精確 PR SHA Checkout
候選工作樹，交由可信 `run_task(...,sandbox=True)` 啟動已存在的
`bubblewrap` 隔離：唯讀 `/work`、合成 `/dev`、隔離全部 namespaces
（含 network）、`--clearenv`、`-I -S` Python、40 秒時限。
沙箱內只執行 Candidate Dispatcher 的模擬 Owner/Runner CLI 與
Stub Codex，輸出固定 `CANDIDATE_DISPATCHER_PREMERGE_SWPC_BWRAP_STUB_PASS`
並由可信 Dispatcher 驗證 SHA256。若 bwrap 缺少、不支援 userns
或隔離條件不成立則 Fail Closed，不得降級為裸執行。這條路徑
實際執行 Candidate Dispatcher 程式碼，但**不啟動真 Codex、不核可
SWPC 硬體權限，也不代表完整 Path 3 Agent E2E**。


## 五、Gate 1 — 推薦與選擇矩陣

| 問題 | Path 1 | Path 2 | Path 3 |
| --- | --- | --- | --- |
| Chat／Work Mode 都能作為入口？ | 是 | 是 | 是 |
| 主要實際執行者 | ChatGPT＋GitHub-hosted CI | SWPC 固定 CLI | SWPC Codex CLI |
| 需要 SWPC？ | 否 | 是 | 是 |
| 需要 Codex 進行自主迭代？ | 否 | 否 | 是 |
| 需要 PR？ | 程式變更時 | 有程式變更時 | 一般需要 |
| 需要硬體？ | 不會接觸本機硬體 | 視 Gate 1 範圍 | 視 Gate 1 範圍 |
| 優先選用條件 | Host-only 已足夠 | 必須 SWPC，固定命令足夠 | 必須 SWPC，且需 Agent 自主性 |
| 成功證據 | Hosted CI／PR | SWPC CLI 真實執行輸出＋ChatGPT 審閱 | Codex Code／Output／Test Log＋ChatGPT 獨立審閱；需要 PR 時再加 CI |

**Path 的最佳化目標：以最少資源、最小實際權限與最短迴圈，取得能回答工程假設的證據。** 刻意避免把同一個 ARMv7 QEMU 函式測試搬到另一台主機重跑，卻沒有額外測試假設。

### 未來每次 Gate 1 的建議模板

> **工作：** 具體目標與第一個可測量 PASS／FAIL
>
> **推薦：** Path N — 一句話說明為何是最低足夠成本與權限
>
> **實際路徑：** ChatGPT 入口 → GitHub Dispatch／PR → Runner／Executor → Evidence
>
> **變更：** 檔案／環境／使用資源／已核准軟硬體動作
>
> **驗收：** 指定 CI／HIL／Hash／Artifact／清理與恢復條件
>
> **不允許：** 超出 Gate 1 的存取、部署及其他 PR Merge
>
> **按鈕：** 「批准 Gate 1 — Path 1」、「批准 Gate 1 — Path 2」、「批准 Gate 1 — Path 3」；如有必要第 4 顆按鈕「暫緩／修改」。不可執行的路徑需明顯註記，不得提供看似有效的批准。
>
> **批准後：** 自主執行、建立／更新 PR、修正 CI、完成證據、停在 Gate 2；遇阻礙才報告。

建議 Path 必須說明理由，不能強制使用者選擇；使用者普通文字明確選 Path／批准同樣有效。單純點選預設值或看見按鈕並不構成授權。對話介面不能顯示按鈕時，提供最多四個簡短文字選項，不得假裝按鈕存在。

## 六、Gate 1／Gate 2 的職責，及少數無 PR 任務

| 項目 | Gate 1 — Plan Approval | Gate 2 — Merge Approval |
| --- | --- | --- |
| 使用者決策 | 指定工作計畫、Path、許可範圍 | 指定 PR、HEAD 和合併方法 |
| 開發／測試／Codex | 已授權即執行真實環境測試、取得證據、FAIL 則修正重測直到符合驗收，或誠實回報阻礙 | 不啟動同一開發任務、不用 Merge 解鎖缺少的測試 |
| CI／Evidence | 實際觸發、修正、採集、核對 | 檢查現有的 CI、Evidence |
| Merge | 不允許 | 即時核對後才允許 |
| 實體 Z2／LA／DUT／部署 | 必須明確列入 Gate 1 才可操作 | 不因合併而擴權 |
| 範圍有重大變更 | 停止並提出修訂 Gate 1 | 不以 Gate 2 掩蓋超範圍 |

**開發階段強制順序：Gate 1 = Build → Real Run → Evidence Review → Fix/Retest → PR/CI Ready；Gate 2 = Merge Decision。**

目前 GitHub `issue_comment` 的 owner-only Development Mode 入口使用 `main` 的可信 Dispatcher 驗證 Owner、PR HEAD SHA 與指定執行能力，候選工程內容可來自未合併 PR；**文件變更不代表 Runner 已載入新版 Dispatcher**。只有相應 Workflow／Dispatcher 真正合併至 `main` 並實際執行後，才能回報新能力已生效。

**Gate 1 已批准後即可執行**，不額外要求每次 SSH、測試、建立 PR、Draft → Ready 的核准；但工具不通、硬體安全事實不符或需新權限時必須安全停止並回報。經核准而可以到達的 Gate 2，只授權合併該特定 PR。

純唯讀檢測、已有工具的受控測試或產生 Evidence 且不建立／合併 PR 的任務，Gate 1 後完成證據回報即可。**不要為沒有 PR 的任務創造「假 Gate 2」。**

## 七、實證邊界與任務結束報告

每一 Path 完成時必須回報：使用者批准的 Path、真正執行的環境、GitHub Run ID／PR HEAD、測試 PASS／FAIL／NOT_RUN、Artifact 或 SHA256、阻礙、M1 狀態與下一個必要決策。

- GitHub-hosted CI PASS **不是** SWPC CLI PASS。
- SWPC QEMU PASS **不是** 真實 Z2 ARM Cortex-A9 PASS。
- CPU Native 執行 PASS **不是** PS7→AXI→PL 實際順序保證。
- Mock／OpenOCD route candidate／設備型錄 admission **不是** 真實 IC 燒錄驗收。

**本治理文件只記錄執行模式。** 不部署 Dispatcher、不啟用 self-hosted workflows、不操作 SWPC、Codex、Z2、FPGA、LA 或 DUT，也不更動產品 runtime。
