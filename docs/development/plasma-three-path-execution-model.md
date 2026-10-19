# PLASMA — Three-Path Work Execution Model（三路徑工作執行模型）

> **狀態：Owner 已同意採用的工作調度決策；本文件隨 AGENTS.md 的 PR 合併後成為 repo 治理規範。**
>
> **範圍：開發、CI、SWPC 工程工作調度，不是產品 PPU 的八 Site 燒錄排程器。**
>
> **注意：這份文件定義路徑與授權，不代表已部署通用 Dispatcher、觸發任何 Codex Job 或完成硬體驗收。**

本文件與根目錄 [AGENTS.md](../../AGENTS.md) §11.1～11.1B 同步。執行能力和目前已實作的 Workflow 以實際 repository／GitHub runner 狀態為準，不得把架構提議當作實機執行成果。

## 一、第一性原理：用執行邊界，而不是 UI 介面分類

- **ChatGPT Chat** 與 **ChatGPT Work Mode** 都可作為三條 Path 的互動入口；「Work」的工作能力不等同於必須打開「Work Mode」。
- **GitHub Actions** 是 Trigger／受控執行與驗證平台，GitHub-hosted 與 SWPC self-hosted Runner 是不同信任／存取邊界。
- **CLI 與 Codex 不同**：CLI 執行事先固定的指令；Codex 在核准的工作契約內自主修改、測試、迭代。不能把 Codex 存在視為可以任意存取硬體。
- **CI 不等於 CD**：合併 PR 不自動授權部署、重啟、改 FPGA、DUT 電源或燒錄 IC。部署、Runtime 和硬體行為必須明列 Gate 1 授權範圍。
- **Gate 1 選 Path 是授權與執行計畫的一部分**，不是第三個 Gate。

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
  A["Gate 1｜使用者批准 Path 2、確定性命令和資源"]
  B["ChatGPT 建立／確認被授權的 Work Order／Workflow"]
  C["實際觸發 GitHub Actions｜驗證事件與權限"]
  D["SWPC Self-hosted Runner｜固定 CLI／Shell"]
  E["結果／Exit Code／Log／SHA256／Evidence"]
  F{"需要合併程式變更？"}
  G["更新 PR／GitHub CI"]
  H["Gate 2 審查及 Merge to main"]
  I["完成報告｜不需要虛構 Gate 2"]
  A --> B --> C --> D --> E --> F
  F -- "是" --> G --> H
  F -- "否" --> I
```

**執行者：** SWPC Runner 執行已審查的固定 CLI 命令；不是讓 Codex 推理與改碼。CLI 任務不可偷偷轉為 Path 3。沒有符合 Gate 1 條件的已啟用 Trigger／Runner 時，必須回報 `NOT_RUN` 和具體阻礙，不能把批准訊息當作 GitHub Job 已經啟動。

## 四、Path 3 — SWPC Codex Work

**推薦場景：** 必須使用 SWPC 及 Codex 的自主迭代能力，例如多模組問題定位、修復與反覆測試、真實軟硬體整合開發。

```mermaid
flowchart TD
  A["Gate 1｜使用者批准 Path 3／Codex 範圍"]
  B["ChatGPT 實際觸發授權的 GitHub Actions"]
  C["GitHub Authorization｜驗證 Work Order／Actor／SHA／資源"]
  D["SWPC 專用 Runner → Codex CLI"]
  E["Codex 修改／Build／Test／修正／Evidence"]
  F["Codex 或隔離 Publisher 建立 Pull Request"]
  G["GitHub CI／Contracts／核准的 HIL"]
  H{"CI 與驗收證據合格？"}
  I["Codex 在原 Gate 1 權限內修正 PR"]
  J["PR Ready｜Gate 2 使用者審查"]
  K["Merge to main｜不重啟相同 Codex 任務"]
  A --> B --> C --> D --> E --> F --> G --> H
  H -- "否" --> I --> G
  H -- "是" --> J --> K
```

**執行者：** SWPC `plasma-codex` Runner 與 Codex CLI；GitHub Actions 負責真正的調度和 PR CI。已知限制：

1. **批准 Gate 1 ≠ GitHub Workflow 自動發生。** ChatGPT／授權工具必須確實呼叫可用 Trigger，並以 GitHub Job 證據核對是否執行。若無法觸發，報告 `NOT_RUN`；不要求已批准事項再重複授權。
2. 現有 `plasma-codex-*.yml` 為不同工作負載的專用流程，不等同於已啟用任意工作內容的通用 Dispatcher。`docs/architecture/plasma-engineering-dispatch-v1.md` 所述統一 Dispatcher 仍是 contract-only，不能因選 Path 3 就聲稱已上線。
3. Codex 建 PR 時，若使用預設 `GITHUB_TOKEN`，**通常不會觸發新的 `pull_request` workflows**。須確保使用核准的 GitHub App token 或其他受控事件機制，讓必要 CI 真正開始。PR 建立成功不能代替 CI PASS。
4. SWPC Codex 帳號可能已有部分硬體存取權；「軟體專用 Prompt」不是 OS 層隔離。Z2／USB／LA／Power／FPGA／DUT 必須依 Gate 1 和安全契約明確允許才操作。
5. Gate 2 只合併既有審查完成的 PR。合併後的 `main` push 可啟動一般 CI，但**不能重新派發同一項 Codex 開發任務**。

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
| 成功證據 | Hosted CI／PR | SWPC Job／CLI／Evidence | Codex Job＋PR＋必要 CI |

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
| 開發／測試／Codex | 已授權即自動執行，不逐步要求 `continue` | 不再啟動同一開發任務 |
| CI／Evidence | 實際觸發、修正、採集、核對 | 檢查現有的 CI、Evidence |
| Merge | 不允許 | 即時核對後才允許 |
| 實體 Z2／LA／DUT／部署 | 必須明確列入 Gate 1 才可操作 | 不因合併而擴權 |
| 範圍有重大變更 | 停止並提出修訂 Gate 1 | 不以 Gate 2 掩蓋超範圍 |

**Gate 1 已批准後即可執行**，不額外要求每次 SSH、測試、建立 PR、Draft → Ready 的核准；但工具不通、硬體安全事實不符或需新權限時必須安全停止並回報。經核准而可以到達的 Gate 2，只授權合併該特定 PR。

純唯讀檢測、已有工具的受控測試或產生 Evidence 且不建立／合併 PR 的任務，Gate 1 後完成證據回報即可。**不要為沒有 PR 的任務創造「假 Gate 2」。**

## 七、實證邊界與任務結束報告

每一 Path 完成時必須回報：使用者批准的 Path、真正執行的環境、GitHub Run ID／PR HEAD、測試 PASS／FAIL／NOT_RUN、Artifact 或 SHA256、阻礙、M1 狀態與下一個必要決策。

- GitHub-hosted CI PASS **不是** SWPC CLI PASS。
- SWPC QEMU PASS **不是** 真實 Z2 ARM Cortex-A9 PASS。
- CPU Native 執行 PASS **不是** PS7→AXI→PL 實際順序保證。
- Mock／OpenOCD route candidate／設備型錄 admission **不是** 真實 IC 燒錄驗收。

**本治理文件只記錄執行模式。** 不部署 Dispatcher、不啟用 self-hosted workflows、不操作 SWPC、Codex、Z2、FPGA、LA 或 DUT，也不更動產品 runtime。
