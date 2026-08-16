# Plasma SWPC 自動更新與部署指南

SWPC 是 Plasma 的整合測試與 Demo Server。日常部署固定執行：

```text
GitHub main → SWPC fast-forward 更新 → 完整測試 → 重新啟動 → health check
```

管理指令命名為 `plasmactl`，避免與既有燒錄 CLI `plasma` 衝突。

## 1. 指令一覽

| 指令 | 功能 |
|---|---|
| `plasmactl status` | 顯示 Git 版本、工作目錄、systemd 與 Port 狀態 |
| `plasmactl update` | 從 GitHub `main` 做 fast-forward 更新 |
| `plasmactl test` | 執行完整 Python、PL source-layout 與 Web 測試 |
| `plasmactl restart` | 重新啟動三個服務並執行 health check |
| `plasmactl deploy` | 依序執行 update、test、restart |
| `plasmactl logs` | 同時查看三個服務的即時 Log |
| `plasmactl logs server` | 只看 Plasma Server Log |
| `plasmactl logs web` | 只看 Python Gateway Log |
| `plasmactl logs vite` | 只看 Vite Log |

`plasmactl deploy` 是日常建議指令。測試失敗時不會重新啟動服務。

## 2. 第一次在 SWPC 安裝

先更新 repository：

```bash
cd /storage/projects/plasma
git status
git pull --ff-only origin main
```

工作目錄必須是乾淨的，再執行：

```bash
chmod +x scripts/plasmactl
./scripts/plasmactl install
```

安裝程序會：

1. 建立或使用 `software/python/.venv`。
2. 安裝 Python 開發相依套件；venv 沒有 pip 時自動改用 `uv pip`。
3. 執行 `npm ci`。
4. 建立三個 user systemd services。
5. 在 `~/.local/bin/plasmactl` 建立連結。
6. enable 服務，但不立即啟動。

服務沒有立即啟動，是為了避免與 SWPC 目前手動啟動的 Python 或 Vite
程序爭用 Port。

## 3. 第一次從手動程序切換到 systemd

先確認目前的監聽程序：

```bash
plasmactl ports
ps -fp PID
```

必須先用 `ps -fp PID` 確認 PID 確實是 Plasma Server、Gateway 或 Vite，
才能停止。不要使用未限制範圍的 `pkill python` 或 `pkill node`。

停止舊程序後啟動 systemd services：

```bash
plasmactl start
plasmactl status
```

三個服務為：

| systemd unit | 預設 Port | 功能 |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma v3.1 TCP Server |
| `plasma-web.service` | 18080 | Python HTTP Gateway |
| `plasma-vite.service` | 5173 | React/Vite Web Console |

若要讓 user services 在 SWPC 開機、尚未登入時也能啟動，執行一次：

```bash
sudo loginctl enable-linger "$USER"
```

## 4. 日常更新與部署

在 SWPC 執行：

```bash
plasmactl deploy
```

腳本有以下保護：

- 工作目錄有未提交修改時拒絕更新。
- SWPC 有尚未推送的本機 commit 時拒絕更新。
- 只允許 fast-forward，不自動 merge 或 rebase。
- Python 或 Node 相依設定改變時才重新同步相依套件。
- 測試失敗時不重新啟動現有服務。
- restart 後等待並檢查 TCP 9900、Gateway API 與 Vite HTTP；服務啟動較慢時會自動重試。

## 5. 從外面透過 Tailscale SSH 部署

Mac 已在 `~/.ssh/config` 設定 `swpc` alias，因此 SSH 連線使用 `gordon@swpc`。

完整更新、測試與重啟：

```bash
ssh gordon@swpc 'plasmactl deploy'
```

只查看狀態：

```bash
ssh gordon@swpc 'plasmactl status'
```

只從 GitHub `main` fast-forward 更新程式碼，不執行測試或 restart：

```bash
ssh gordon@swpc 'plasmactl update'
```

查看即時 Log（`-t` 會配置互動終端）：

```bash
ssh -t gordon@swpc 'plasmactl logs'
```

### 5.1 Non-interactive SSH 的 PATH

`ssh gordon@swpc 'command'` 使用 non-interactive shell。Ubuntu 的 `~/.bashrc`
通常會在偵測到 non-interactive shell 後提早 `return`，因此如果
`~/.local/bin` 的 PATH 設定寫在該 `return` 之後，SSH 遠端命令可能會出現：

```text
plasmactl: command not found
```

即使 `~/.local/bin/plasmactl` symlink 本身已存在。

SWPC 目前已調整 `~/.bashrc`：在 non-interactive shell 的 early return **之前**，
以有條件的方式將 `$HOME/.local/bin` 加入 `PATH`，避免重複加入。修改 shell
設定前應先備份原始檔案。

等效設定可採用：

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
```

這段必須位於 `.bashrc` 的 non-interactive early return 之前。

修改後，從 Mac 驗證：

```bash
ssh gordon@swpc 'command -v plasmactl && plasmactl status'
```

預期 `command -v` 回傳：

```text
/home/gordon/.local/bin/plasmactl
```

並且 `plasmactl status` 能正常顯示 Plasma Git、systemd services 與 Port 狀態。

若 PATH 尚未修正，可暫時使用完整路徑：

```bash
ssh gordon@swpc '~/.local/bin/plasmactl status'
```

公開 Web Console 網址：

```text
https://plasma.open4th.com
```

Tailscale 網址 `https://swpc.tail820e64.ts.net` 保留作為內部維護入口；
Gateway 的內部維護網址為 `https://swpc.tail820e64.ts.net:8443`。

## 6. 設定檔

第一次安裝會建立：

```text
~/.config/plasma/plasmactl.env
```

預設內容包括：

```bash
PLASMA_REPO=/storage/projects/plasma
PLASMA_BRANCH=main
PLASMA_NPM=/home/gordon/.nvm/versions/node/v22.23.2/bin/npm
PLASMA_UV=/home/gordon/.local/bin/uv
PLASMA_GATEWAY_HOST=0.0.0.0
PLASMA_GATEWAY_PORT=18080
PLASMA_CORS_ORIGIN='*'
PLASMA_VITE_HOST=127.0.0.1
PLASMA_VITE_PORT=5173
```

公開部署使用下列 API Base：

```bash
PLASMA_PUBLIC_API_URL=https://plasma.open4th.com
```

API Base 後面不能加入 `/api`；Web Console 會自行在 Base URL 後附加 API
路徑。

Cloudflare Tunnel 只需將整個 hostname 代理到 Vite：

```text
plasma.open4th.com → http://127.0.0.1:5173
```

Vite 會保留原始路徑，將 `/api/*` 代理到：

```text
http://127.0.0.1:18080
```

建議使用 Cloudflare Access 保護整個 `plasma.open4th.com` hostname。

既有 Tailscale 網址仍保留作為內部維護入口，不受公開 Cloudflare 路由影響。

修改設定檔後，重新產生 unit 並啟動：

```bash
cd /storage/projects/plasma
./scripts/plasmactl install
plasmactl restart
```

Gateway 預設監聽 `0.0.0.0:18080`，只能透過 UFW、Tailscale ACL 或反向代理
限制在可信任網路，不應直接將 18080 暴露至公用 Internet。

## 7. 疑難排解

查看狀態：

```bash
plasmactl status
```

查看各服務最近 100 行並持續追蹤：

```bash
plasmactl logs server
plasmactl logs web
plasmactl logs vite
```

systemd 詳細狀態：

```bash
systemctl --user status plasma-server plasma-web plasma-vite --no-pager
```

如果顯示 `Address already in use`，先執行：

```bash
plasmactl ports
```

找出並確認舊程序後再停止它，不能直接終止不明 PID。
