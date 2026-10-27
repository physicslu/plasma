# SWPC Z2 工具箱：Blue Pill Stage A

這個開發工具由 SWPC 直接執行。它在 SWPC 啟動 LA2016 擷取，再透過已登錄
的 SSH／sudo 路由執行 Z2 PS 上的受保護 MMIO 診斷。它不下載 FPGA、不執行
OpenOCD、不操作 Flash，也不透過 Path 2 或 Path 3 Runner。

## 接線與一鍵命令

先**移除 Blue Pill**，確認 PmodBB P1／P2 沒有其他主動驅動器。LA 接線：
CH0、CH3 接 PmodBB P1（CLOCK）；CH1 接 PmodBB P2（DIO）；CH2 接 Z2
3.3 V；LA GND 接 Z2 GND。PWM1 保持關閉。只有實體條件已成立，才在
SWPC 的 repo 根目錄執行：

```bash
python3 scripts/z2-toolbox.py stage-a --bluepill-removed
```

可用 `--output-dir /path/to/new-directory` 指定新的證據目錄。預設目錄
為 `.work/z2-toolbox/<UTC 時間>/`，內含 `stage-a.sr` 原始波形與
`report.json`。工具要求目錄尚不存在，不覆寫先前結果。退出碼 0 需要
MMIO 內部檢查、CH2 高電位參考，以及 CH0／CH1／CH3 各有高低邊緣；
否則為 1，並在報告中分列 `internal_pass` 和 `la_pass`。LA 是數位門檻
量測，不能報告準確電壓。

PS 程式受版本管理於 `scripts/z2/bluepill-stage-a-ps.py`，目前已安裝於
`/opt/plasma/bluepill-manual-stage-a-20261027/ps-manual-stage-a.py`。SWPC
執行時在 PS 上先核對安裝檔與 repo 來源的 SHA256；不一致即停止，不驅動
SWD。PS 程式仍須通過原有 Root source pin、Boot ID、Image／Manifest、
ABI、owner lock 與 MMIO 空閒檢查，才執行 `0x04 → 0x07 → 0x04`，
各保持 3 秒，最後寫 `0x02` 使 CLOCK 低且 DIO Hi-Z。Image 保持載入。
若 Z2 重開機或更換 Image，需先重新評估對應身分與實體安全；不可改
Boot ID 常數繞過檢查。

SWPC 使用目前使用者私有的 `~/.config/plasma/z2-login-smoke.json`、
`~/.ssh/plasma_z2_ed25519` 與 `~/.ssh/known_hosts` 中已確認的 Z2 Host Key，
以及 `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`。SSH／sudo 密碼
只經 stdin 提供，報告不保存憑證或 Z2 網址。LA 操作受
`/run/lock/plasma-la2016.lock` 保護，並在確認取樣開始後才觸發 PS。

先前手動版的 PS 執行環境、精確雜湊與操作說明也已安裝在 Z2：
`/opt/plasma/bluepill-manual-stage-a-20261027/PS-MANUAL-RUN.md`。
本工具的 `report.json` 記錄當次 PS Python／架構／Boot ID、腳本 SHA、
MMIO 讀回、LA 取樣與波形 SHA；當次實測結果以該報告為準。
