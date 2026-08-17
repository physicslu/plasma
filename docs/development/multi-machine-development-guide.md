# Plasma 多電腦開發指南

> 專案：`physicslu/plasma`  
> 目前標準：SWPC 中央 Linux 工作區 + VS Code Remote - SSH clients  
> 更新日期：2026-08-17

###### tags: `Plasma` `GitHub` `VS Code` `Remote-SSH` `FPGA` `Python` `Web`

---

## 1. 現行架構

Plasma 不再把「每台電腦各自維護完整開發環境與 repository clone」作為日常標準。
目前的標準是：

- **GitHub**：已發布 Git history、Pull Request 與 CI 的 source of truth。
- **SWPC**：主要 Development / Integration Linux workspace。
- **Mac、SHNB、DESKTOP-1**：透過 VS Code Remote - SSH 操作 SWPC。
- **Z2**：embedded runtime、PS/PL integration 與 hardware validation target；不是日常程式編輯主機。

```text
                    GitHub
                      ^
                      |
                 branch / PR
                      |
                     SWPC
        /storage/projects/plasma
          /        |         \
         /         |          \
      Mac        SHNB      DESKTOP-1
      VS Code     VS Code     VS Code
         \         |          /
          +---- Remote SSH ---+

                     |
                     | approved target validation
                     v
                     Z2
```

這個模型的目的不是把 GitHub 拿掉，而是避免每台 client 都維護不同版本的 Python、
Verilator、cocotb、Node、Vivado 與 build artifacts。

---

## 2. 四台電腦的角色

| 主機 | 正式角色 | 正常 Plasma 使用方式 | 本機特殊用途 |
|---|---|---|---|
| SWPC (Linux) | Primary Development & Integration Host | 直接使用 `/storage/projects/plasma` | Verilator、cocotb、pytest、Python venv、Node/Web、Vivado |
| Mac | Primary Engineering Client | VS Code Remote - SSH → SWPC | Ollama / local AI，可選 Continue/Cline |
| SHNB (Dell) | Portable Engineering Client | VS Code Remote - SSH → SWPC | Windows Vivado 可保留作隔離實驗，不作正式 build source of truth |
| DESKTOP-1 | Company Thin Client | VS Code Remote - SSH → SWPC | 盡量不保存 Plasma source/toolchain/firmware |

### 2.1 SWPC

SWPC 是日常開發的實際執行環境：

```text
SSH:        gordon@swpc
Repository: /storage/projects/plasma
```

FPGA、Python、Web 等 deterministic tools 應以 SWPC 已驗證環境為準。

### 2.2 Mac

Mac 是主要 UI/client，並可執行本機 Ollama 與 local AI。

```text
Mac AI inference
      |
      | edit / agent interaction
      v
VS Code Remote - SSH
      |
      v
SWPC Plasma workspace
```

Local AI 可以協助編輯 SWPC workspace，但 deterministic compile/test 仍由 SWPC 執行。

### 2.3 SHNB

SHNB 正常工作模式仍是 Remote - SSH → SWPC。
若 Windows 上已安裝 Vivado，可保留作獨立 FPGA GUI experiment；正式 Plasma integration
結果仍回到 SWPC 驗證，避免建立第二套不受控 toolchain。

### 2.4 DESKTOP-1

公司電腦應盡可能維持 thin-client 模式：

- VS Code
- Remote - SSH
- 必要的 SSH/Tailscale access

除非有明確需要且符合公司政策，不要在 DESKTOP-1 建立完整 Plasma toolchain、複製
firmware artifacts、credentials 或長期維護另一份 repository clone。

---

## 3. Repository 與工具位置

主要 repository：

```text
/storage/projects/plasma/
├── .vscode/
│   ├── tasks.json
│   ├── extensions.json
│   └── settings.json
├── pl/
│   ├── env.sh
│   ├── rtl/
│   ├── targets/
│   ├── tools/
│   ├── verification/
│   └── build/
├── software/python/
├── software/web/
└── docs/
```

重要 Python environment boundary：

```text
pl/.venv/                 FPGA verification
software/python/.venv/    Plasma software/server
```

不要因為 VS Code 只能顯示一個 global Python interpreter，就把兩個 environment 混成一個。

---

## 4. 每台 client 第一次設定

### 4.1 必要本機工具

Mac、SHNB、DESKTOP-1 至少需要：

- Visual Studio Code
- OpenSSH client
- VS Code Remote - SSH
- 可連線到 SWPC 的網路路徑（例如既有 Tailscale/SSH setup）

不需要為正常 Remote-SSH workflow 在每台 client 重裝：

- Verilator
- cocotb
- FPGA `pl/.venv`
- Plasma software Python venv
- Node/Web build environment
- Vivado

這些工具應由 SWPC 提供。

### 4.2 Remote - SSH

VS Code：

```text
Cmd/Ctrl + Shift + P
→ Remote-SSH: Connect to Host...
→ SWPC
```

連線後開啟：

```text
/storage/projects/plasma
```

左下角必須顯示 Remote SSH host。若 terminal prompt 不是 SWPC，先確認位置再執行命令。

---

## 5. VS Code Workspace 標準

Repository 會提供：

```text
.vscode/tasks.json
.vscode/extensions.json
.vscode/settings.json
```

### 5.1 Workspace recommended extensions

建議安裝：

- Remote - SSH
- SystemVerilog - Language Support
- Surfer waveform viewer
- Python
- Pylance
- ESLint
- Prettier

Mac 的 Ollama/Continue/Cline、theme、font 等屬 machine/personal settings，不放進 shared
workspace requirements。

### 5.2 SystemVerilog compile policy

SystemVerilog extension 的單檔 compile-on-save / compile-on-open 會被 workspace 關閉。
原因是 Plasma 採 target-based build：真正 build unit 是 `pl/targets/*.toml`，不是單一 `.sv`。

FPGA 正常操作：

```text
開啟 RTL
   |
   | macOS:   Cmd + Shift + B
   | Windows/Linux: Ctrl + Shift + B
   v
FPGA: Verify Current Target
   |
   v
pl/env.sh
   |
   v
pl/tools/fpga.py
   |
   +-- target resolution
   +-- Verilator lint
   +-- cocotb / pytest
```

加入新 RTL 時通常只新增/修改 target manifest；不要為每個 `.sv` 複製 VS Code task。

---

## 6. Git 工作模式

雖然日常編輯集中在 SWPC，GitHub 仍是 publication/integration source of truth。

開始 code-changing work 前：

```bash
cd /storage/projects/plasma
git status -sb
git branch --show-current
git fetch origin main
```

乾淨的 local `main` 若只落後遠端：

```bash
git switch main
git pull --ff-only origin main
```

新功能使用 feature branch：

```bash
git switch -c agent/<feature-name>
```

AI/agent 可在 feature branch 完成 routine implementation、test、commit、push、PR 與 CI repair；
merge 到 `main`、deployment/restart、hardware-affecting operation 仍依 root `AGENTS.md` approval gate。

不要用 `git reset --hard`、`git clean -fd` 或 force push 作為一般同步方法。

---

## 7. FPGA 開發

日常 FPGA functional verification 不需要直接輸入完整 command line；優先使用 VS Code default
build task。

必要時 CLI 等價入口：

```bash
cd /storage/projects/plasma
source pl/env.sh
python pl/tools/fpga.py list
python pl/tools/fpga.py verify <target>
```

Target manifest 位於：

```text
pl/targets/
```

Build artifacts 位於：

```text
pl/build/
```

`pl/build/` 與 `pl/.venv/` 不進 Git。

Vivado synthesis/implementation/bitstream 與 Z2 hardware validation 是後續不同 gate；
Verilator/cocotb PASS 不代表 timing closure 或 hardware PASS。

---

## 8. Python 開發

### FPGA verification

使用：

```text
pl/.venv/
```

正常由 FPGA VS Code tasks 啟動，不要用這個 environment 對整個 repository 任意跑 pytest。

### Plasma software

使用：

```text
software/python/.venv/
```

正式直接測試入口：

```bash
cd /storage/projects/plasma/software/python
.venv/bin/python -m pytest -q
```

不要為了讓錯誤 environment 跑過測試，就把另一個子專案的 dependency 裝進去。

---

## 9. Web 開發

Web source 位於：

```text
software/web/
```

正常 checks 以 repository `package.json` 與 root `AGENTS.md` 為準：

```bash
cd /storage/projects/plasma/software/web
npm run lint
npm test
npm run validate:artifact
```

Node/npm 是 SWPC 開發與 build toolchain 的一部分；正常 thin client 不需要另一套 Node 環境。

---

## 10. SWPC runtime 與 ports

目前 SWPC operational ports：

| Service | Port |
|---|---:|
| Plasma Server | 9900 |
| Python HTTP REST Gateway | 18080 |
| Web Console development/demo service | 5173 |

`8080` 不是目前 SWPC Gateway operational port；不要依舊文件把部署改回 8080。

Service/deployment 操作以：

```text
scripts/plasmactl
```

為準。部署與 restart 是 protected operational gate，不因 Remote-SSH 方便就跳過 approval。

---

## 11. Local clone 何時才合理

Client 本機 clone 不是禁止，而是從「default workflow」降為「specific isolated use case」。
例如：

- Mac local AI sandbox 需要完全隔離的 experiment
- SHNB Windows Vivado 的獨立 project experiment
- 離線工作，無法連 SWPC

若建立 local clone：

1. 使用獨立 branch。
2. 不要與 SWPC 同時改同一 branch 的相同檔案。
3. 要跨機接續前先 commit/push。
4. 最終 integration 仍回到 SWPC 驗證。
5. 不把 local build artifacts 當成 repository source of truth。

---

## 12. 快速檢查表

### 在任一 client 開始工作

- [ ] VS Code 已連到 `SWPC`。
- [ ] Workspace 是 `/storage/projects/plasma`。
- [ ] `git status -sb` 沒有不明修改。
- [ ] 正在正確 branch。
- [ ] Workspace recommended extensions 已安裝。

### FPGA

- [ ] 開啟的 RTL 已屬於正確 target manifest。
- [ ] 使用 `Cmd/Ctrl + Shift + B` 執行 `FPGA: Verify Current Target`。
- [ ] Lint PASS。
- [ ] cocotb/pytest PASS。
- [ ] 沒有把 `pl/build/` 或 `.venv/` 加入 Git。

### Commit / PR

- [ ] 看過 diff。
- [ ] 跑過 affected-scope validation。
- [ ] 只 stage intended files。
- [ ] Push feature branch。
- [ ] CI PASS 後才進入 merge approval gate。

---

## 13. Related documents

- `docs/development/vscode-remote-workspace.md`
- `docs/development/fpga-development-guide.md`
- `docs/development/fpga-verification-guide.md`
- `docs/development/local-ai-development-guide.md`
- `docs/development/swpc-deployment.md`
- root `AGENTS.md`
- `pl/AGENTS.md`
