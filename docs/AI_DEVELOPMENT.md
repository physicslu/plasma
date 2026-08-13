# Plasma AI 協同開發流程

本文件定義 `physicslu/plasma` 的 AI 協同開發方式。`main` 是穩定主線；功能、修正與實驗均應在獨立 branch 完成，經測試與審查後才合併。

## 標準流程

```text
需求
  → 建立 branch
  → AI 修改
  → Unit Test
  → Integration Test
  → Review diff
  → Commit
  → Push branch
  → Pull Request
  → Merge main
```

### 1. 需求與範圍

開始前先說清楚目標、允許修改的檔案、驗收條件、安全限制，以及是否允許安裝套件、停止服務或操作硬體。AI 應先閱讀相關程式、設定、測試、文件與 CI，不得擴大修改範圍。

### 2. 建立 branch

從乾淨且最新的 `main` 開始：

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/<topic>
```

不要直接在 `main` 開發，也不要 force push。

### 3. AI 修改

AI 僅修改已核准的檔案，保留既有架構與使用者變更。不得自行使用 `sudo`、執行 `npm update`、升級 dependencies、修改 Vivado 安裝，或停止 Apache/Nextcloud 與其他未納入任務的服務。

### 4. Unit Test

依修改範圍執行最小且足夠的單元測試：

```bash
# Python
cd software/python
.venv/bin/python -m pytest -q

# Web（包含 build 與 Node tests）
cd software/web
npm test

# FPGA repository checks
python3 -m unittest discover -s pl/tests -v
```

Web 變更通常也應執行 `npm run lint` 與 `npm run validate:artifact`。

### 5. Integration Test

確認變更與相鄰元件能共同運作。例如 Web 應連到 Python Gateway，Gateway 應連到 Plasma Server；涉及硬體時須區分 Mock Interface 與實體板卡測試。SWPC prototype 目前 CH0/CH1 為 Mock Interface，測試結果不可誤稱為實體燒錄結果。

### 6. Review diff

```bash
git status
git diff --check
git diff
```

逐檔確認沒有憑證、`.env`、log、`.venv`、`node_modules`、Vivado 或其他 build 產物，也沒有非預期修改。AI 必須回報 changed files、tests 與 diff 概要。

### 7. Commit、Push 與 PR

只 stage 本次工作的明確檔案，使用能描述目的的 commit message，push feature branch 後建立 Pull Request。PR 應說明變更、原因、測試結果、風險與未完成事項。CI 與人工 review 通過後才 merge 到 `main`。

### 8. Merge main

合併後，各工作環境再同步穩定主線：

```bash
git switch main
git pull --ff-only origin main
```

## 平行開發：branch 與 git worktree

Web、Python、FPGA 可使用不同 branch 平行開發，例如：

- `feature/web-<topic>`
- `feature/python-<topic>`
- `feature/fpga-<topic>`

同一台電腦需要同時工作時，可為每個 branch 建立獨立 `git worktree`。每個 worktree 應使用獨立的產物目錄與開發 port，且不得共用或覆寫另一個 worktree 的 `.venv`、`node_modules`、Vivado build、log 或執行中服務。

跨子系統介面變更應先約定 API、資料格式、register map 或驗收測試，再由各 branch 平行實作。整合 branch 或 PR 必須驗證介面相容性，最後依依賴順序合併，避免 Web、Python 與 FPGA 各自通過測試但整體無法運作。

## SWPC 執行環境注意事項

- Plasma Server 使用 port `9900`。
- Python Web Gateway 使用 port `18080`。
- Vite 使用 port `5173`。
- port `8080` 已由 Apache/Nextcloud 使用，不可占用或停止該服務。
- Tailscale Web：`https://swpc.tail820e64.ts.net`。
- Tailscale API：`https://swpc.tail820e64.ts.net:8443`。
