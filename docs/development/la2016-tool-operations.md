# KINGST LA2016 工具操作手冊：被動 SWD 擷取與已實測 PWM Loopback

**狀態：Reference / 2026-10-16 與 2026-10-23 實際驗證。** 本文件整理 PLASMA 已經成功執行的 LA2016 操作，而非新硬體能力或普遍授權。真實量測必須另有 Owner 授權，排他使用 USB Device，且不得讓 LA2016 產生未授權電氣輸出。

## 1. 工具版本、設備與先決條件

| 項目 | 曾成功的組態 |
| --- | --- |
| KINGST 裝置 | LA2016，USB VID:PID `77a1:01a2`；**USB bus.device 每次都要重新查** |
| sigrok CLI | `0.8.0-git-f44dd91` / libsigrok `0.6.0-git-883c2ac` / `kingst-la2016` Driver |
| AppImage | `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage` |
| AppImage SHA256 | `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475` |
| 執行方式 | AppImage **必須**使用 `--appimage-extract-and-run`；先恢復原本 `SIGROK_FIRMWARE_PATH` |
| Device Lock | SWPC `/run/lock/plasma-la2016.lock`，同時確認 USB 沒有別的程式占用；單靠 advisory lock 不夠 |
| 2026-10-23 被動 SWD | CH0 = Blue Pill PA14/SWCLK、CH1 = PA13/SWDIO、CH2 = 3.3V 邏輯狀態；共地 |
| 2026-10-16 獨立 Loopback | KINGST PWM1 → **同一台** KINGST CH0；與 Blue Pill SWD 測試是完全不同接線 |

**動態辨識：** 本手冊只固定 USB VID:PID `77a1:01a2` 作為識別條件，不固定 `busnum`、`devnum`、`/dev/bus/usb/...` 路徑；Codex／Supervisor 必須在每一次工作執行時查詢並檢查唯一設備、存取權限及佔用狀態。

**相容性注意：** 系統內建 `sigrok-cli` 不必然包含 `kingst-la2016` 驅動，不能因為 PATH 有 sigrok 就替代上述指定 AppImage。歷史證據沒有要求在每次採樣時重新上傳 LA FPGA Firmware；不應額外加入未知初始化步驟。

### 受控初始化（兩種模式共用）

```bash
SIGROK_APPIMAGE=/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage
sha256sum "$SIGROK_APPIMAGE"
# 比對上方已釘選的完整 SHA256；不符合就停止。

# 先沿用既有受控工作環境所設定的 SIGROK_FIRMWARE_PATH。
# 若未設定，Codex 要在現場查找「既有」kingst-la-01a2.fw，
# 只搜尋既有受控工具／韌體／工作目錄，選定單一來源；不可猜路徑或下載。
if [ -z "${SIGROK_FIRMWARE_PATH:-}" ]; then
  mapfile -t FW_FILES < <(
    for root in /opt/plasma /usr/share/sigrok-firmware /usr/local/share/sigrok-firmware "$PWD/.work"; do
      [ -d "$root" ] || continue
      find "$root" -type f -name kingst-la-01a2.fw -print 2>/dev/null
    done | sort -u
  )
  [ "${#FW_FILES[@]}" -eq 1 ] || {
    echo "LA_FIRMWARE_MISSING_OR_AMBIGUOUS (search previous verified SWPC context)" >&2
    exit 1
  }
  export SIGROK_FIRMWARE_PATH="$(dirname "${FW_FILES[0]}")"
fi
[ -r "$SIGROK_FIRMWARE_PATH/kingst-la-01a2.fw" ] || {
  echo "LA_FIRMWARE_RESOURCE_NOT_READABLE" >&2
  exit 1
}
# 在實際啟動前核對既有資源來源與 SHA（若歷史紀錄有其 digest）。
# 不把本機私有資源位置或未公開的 USB 詳細識別碼寫入 Git。

# 動態查找 USB 77a1:01a2；每次執行時從 sysfs 重新取得 busnum/devnum。
# 沿用 scripts/plasma-codex-la2016.py 的唯一裝置、權限、fuser 策略。
# 不使用歷史 USB 節點值，也不輸出 USB 序號。
LA_CONN="$(python3 - <<'PY'
import os, pathlib, stat, subprocess, sys
root = pathlib.Path('/sys/bus/usb/devices')
found = []
for entry in root.iterdir():
    try:
        vid = entry.joinpath('idVendor').read_text().strip().lower()
        pid = entry.joinpath('idProduct').read_text().strip().lower()
    except (OSError, ValueError):
        continue  # 其他 USB 介面節點並非獨立 USB Device
    if (vid, pid) != ('77a1', '01a2'):
        continue
    try:
        bus = int(entry.joinpath('busnum').read_text())
        dev = int(entry.joinpath('devnum').read_text())
        if not 1 <= bus <= 999 or not 1 <= dev <= 999:
            raise RuntimeError('LA_USB_BUS_DEVICE_INVALID')
        node = pathlib.Path(f'/dev/bus/usb/{bus:03}/{dev:03}')
        if not stat.S_ISCHR(node.stat().st_mode) or not os.access(node, os.R_OK | os.W_OK):
            raise RuntimeError('LA_USB_DAC_DENIED')
        found.append((f'{bus}.{dev}', node))
    except (OSError, ValueError) as exc:
        raise RuntimeError('LA_USB_SYSFS_OR_NODE_ERROR') from exc
if len(found) != 1:
    raise SystemExit(f'LA2016_UNIQUE_USB_MAPPING_FAILED: {len(found)} candidates')
try:
    check = subprocess.run(['fuser', '-s', str(found[0][1])], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except (OSError, subprocess.TimeoutExpired) as exc:
    raise SystemExit('LA_USB_OWNER_CHECK_UNAVAILABLE') from exc
if check.returncode != 1:  # 0=busy, 1=free, other=uncertain
    raise SystemExit('LA_USB_BUSY_OR_OWNER_UNCERTAIN')
print(found[0][0])
PY
)" || exit 1
test -n "$LA_CONN" || exit 1
export LA_CONN

# 若要同時比較 ST-LINK，從當前 USB 列舉查詢，不用歷史 Bus/Device 值：
# lsusb -d 0483:  # 只作盤點；實際 ST-LINK 身分使用 st-info --probe 確認

# 下列命令是輸入採樣；沒有 PWM1 enable / generator 輸出。
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 3 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config samplerate=5m --channels CH0,CH1,CH2 \
  --samples 50000000 --output-file "$OUT"
```

`OUT` 應事先指定為本次唯一且新的 `.sr` 輸出檔。上述命令並非每次都會成功：USB 存取權限、資源路徑、採樣通道／接線及設備占用狀態都要在現場確認。**在實際的 SWD 嘗試開始之前，應先啟動 LA 採樣並保持重疊時間窗**；否則不能稱為該失敗事件的波形。

### 韌體資源問題的已知案例（2026-10-26）

當 `SIGROK_FIRMWARE_PATH` 未設定／指錯位置，驅動曾顯示：

```text
Failed to open resource 'kingst-la-01a2.fw'
kingst-la2016: MCU firmware upload failed.
No devices found.
```

先確認**當前程式環境**的 `SIGROK_FIRMWARE_PATH` 是否有值，以及該路徑是否包含可讀取的、來源可驗證的 `kingst-la-01a2.fw`；再確認 AppImage SHA256、目前 USB device/permission，與未被其他程式占用。**當前故障的最終根因仍須以新的實際 Driver 初始化 PASS 證明**，不能把「曾經成功」視為本次已成功。不得從任意網站下載未知韌體，不得為此修改 FPGA SWD RTL。

## 2. 模式 A：被動 SWD 邏輯波形（PLASMA 當前用途）

**電氣約束：** LA2016 僅連接共地與輸入通道，不得在這個模式啟用 PWM1。**ST-LINK 與 Z2 PL 是兩個不同的 SWD 主控，不得同時驅動 Blue Pill。** 目前比較用的成功基準來自 2026-10-23 STLINK-V3SET；Z2 失敗測試則只能由 Z2 單獨驅動。

曾成功的設定：

- 採樣率 `samplerate=5m`，50,000,000 samples，即 10 秒名義窗口。
- `CH0,CH1,CH2` 分別 SWCLK、SWDIO、3.3V Digital High/Low；歷史門檻 1.40V。
- 對照三輪 Program + 三輪 Verify 各 `*.sr` 原始波形；每輪 `*-decode.txt` 含 SWD Line Reset、JTAG→SWD、IDCODE、ACK `OK` 或 `WAIT`。
- Golden 參考中確實量測到 `DPIDR 0x1BA01477`；Z2 的 `Error connecting DP: cannot read IDR` 不是等效成功結果。
- 優先比較 SWCLK 週期分布、線路 Reset、選擇序列、SWD request、SWDIO turnaround、ACK、資料和 parity，報告**第一個可量測的偏差**。邏輯分析儀不能單獨證明訊號振幅／類比品質。
- 觀察到成功參考的主要 SWCLK 週期約 10 µs，但 `st-flash --freq=100` 報告 50 kHz；此差異尚未解決，不能據此宣稱時脈量測已校準。

封存資料與可重算測試：

```bash
# 不開啟任何 USB、不操作 DUT，只重新驗證封存的六份 SWD 原始 .sr
python3 docs/evidence/stlink-stm32f103-swd-reference/2026-10-23/verify.py
```

[六份真實 ST-LINK SWD 波形與收據](../evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md)；搭配 [ST-LINK 工具操作手冊](stlink-swd-tool-operations.md)。

## 3. 模式 B：KINGST PWM1 → 同機 CH0 Loopback（只供獨立治具）

**警告：PWM1 是實際電氣輸出。** 只在已確認的「PWM1 → 同一台 LA2016 CH0」獨立回路下，且本次明確授權時使用。**Blue Pill / Z2 SWD 接線時絕對不能執行以下 PWM Enable 命令。**

以下命令形式是 2026-10-16 **真正實測 PASS** 的兩組設定（實測 1 kHz 50% 與 2 kHz 25%，各 1 MHz 採樣）。必須在整個 Supervisor 工作中持續佔有 LA lock，並在包括錯誤和中斷在內的所有退出分支關閉 PWM：

```bash
# 先確認已改成 OWNER 授權的同機 PWM1->CH0 Loopback 接線與工具環境
OUT="<new loopback waveform filename>"
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 4 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config samplerate=1m \
  --config channel_group=PWM1:output_frequency=1000:output_duty_cycle=50:enabled=on \
  --channels CH0 --samples 100000 --output-file "$OUT"

# 第二組歷史測試只把 channel_group 更換成：
# PWM1:output_frequency=2000:output_duty_cycle=25:enabled=on
```

**必備安全清理（不可省略）：**

```bash
# Supervisor 的 finally/error/termination 路徑都必須執行這個關閉命令
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 4 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config channel_group=PWM1:enabled=off --set

# 再獨立採樣 CH0，確認實體線路持續 Low 且沒有任何上升緣
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 4 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config samplerate=1m --channels CH0 \
  --samples 20000 --output-file "$OUT_OFF"
```

2026-10-16 的兩組 OFF 波形各有 22,496 實際 samples、全部 Low、零 edges；要求樣本數 `20000` 可能不等於儀器實際回傳長度。**`--set enabled=off` Exit 0 只代表指令完成，不可取代實體 CH0 OFF 波形核對。** 如 OFF 未能證明，不宣稱安全關閉成功。

封存資料重算（純離線）：

```bash
python3 docs/evidence/la2016-pwm-loopback/2026-10-16/verify.py
```

[2026-10-16 PWM Loopback 成功紀錄](../evidence/la2016-pwm-loopback/2026-10-16/README.md)。

## 4. 必須保存的最小證據

每一次真正的 LA 工作都應保存：

1. LA 裝置身分（不公開獨特序號／即時 bus address）、AppImage SHA256、韌體資源的存在與來源校驗狀態、操作員及 Device Lock 狀態。
2. 模式是 **Passive Input** 還是 **PWM Loopback**、實際連線與通道配置、採樣率、Requested／Actual samples、threshold 與捕捉期間。
3. 原始 `.sr`、命令 Exit Code、帶時間戳記的控制程式／OpenOCD 操作收據、原始檔案 SHA256、decoder output、導出比較報告。
4. 如曾使用 PWM，保留關閉命令 Exit Code 與**另外擷取**的 OFF 驗證波形。
5. 成功參考與失敗波形分別註明證據來源與日期；沒有新擷取就填 `NOT_RUN`，不可用舊波形冒充本次 Z2 PASS。

本文件不更動系統 sigrok、udev、Kernel、FPGA image、DUT Flash、ST-LINK 配線或電源控制。實際執行仍以當次 Owner 授權與硬體 Owner/Lock 為準。
