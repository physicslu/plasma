# ST-LINK SWD 工具操作與 LA2016 成功波形參考

**狀態：Reference / Operator-observed (2026-10-23)。** 此文件是既有 STLINK-V3SET → STM32F103C8T6（Blue Pill）實測操作的可重用工具手冊，不是一般性硬體操作授權。GitHub Actions 或 Codex 讀取本文件，不等於獲得操作 USB、DUT Flash、電源或 Reset 的權限。

## 1. 硬體及工具分工

| 項目 | 2026-10-23 已觀察內容 |
| --- | --- |
| SWD 主控 | STLINK-V3SET，韌體 V3J17S1；操作端工具 `st-flash 1.7.0`、`st-info` |
| DUT | STM32F103C8T6 Blue Pill；`st-info --probe` 回報 chip ID `0x0410`、Flash 64 KiB、SRAM 20 KiB |
| ST-LINK 接線 | T_VCC（VTref）、GND、SWCLK、SWDIO；NRST 曾聲明連接，但 **電氣連通未驗證** |
| 波形量測 | KINGST LA2016 `77a1:01a2`，CH0=Blue Pill PA14/SWCLK、CH1=PA13/SWDIO、CH2=3.3V 邏輯觀察、共地 |
| LA 軟體 | 已鎖定 sigrok AppImage，SHA256 `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`；`kingst-la2016` Driver，sigrok-cli `0.8.0-git-f44dd91` |
| ST-LINK OpenOCD 參考 | 0.11.0，曾回報實際 VTref `3.316944 V` |

**連線排他性：** 使用 ST-LINK 當 SWD 主控時，Z2／Pmod 的 SWCLK／SWDIO 不得同時驅動同一 DUT。切換到 Z2 PL 主控時也一樣，ST-LINK SWD 輸出必須先隔離。LA2016 僅作為被動輸入。不得把「ST-LINK 成功時的接線」視為「兩個 Adapter 可同時連接驅動」的授權。

**電壓前置條件：** 2026-10-23 在 ST-LINK T_VCC 未連接時，OpenOCD 僅量得約 `0.003189 V`，已停止燒錄；接上 T_VCC 後才看到 `3.316944 V`。不得只因 CH2 數位 HIGH（閾值 1.40V）即宣稱類比供電品質通過。

## 2. 已實測的 ST-LINK CLI 操作

以下為 **2026-10-23 成功紀錄中的命令形式**。此處僅作文件保存；執行前仍須由具權限的操作流程確認單一 SWD Owner、供電電壓、USB 狀態、目標身分、Flash 位址、韌體來源與備份／回復計畫。

```bash
# 0. Codex/Operator 每次從當前 USB 裝置列舉確認 ST-LINK；不使用固定 Bus/Device 路徑。
#    lsusb 僅協助盤點，不代表已取得 ST-LINK 排他操作權。
lsusb -d 0483:

# 1. 由 ST-LINK 工具動態選取已連接的裝置，探測 target chip/flash，不寫入。
#    若有多個 ST-LINK，先明確識別唯一 DUT/Probe，禁止默認選第一個。
st-info --probe

# 2. 實際執行過的 ST-LINK 寫入命令，具有破壞性；
#    僅在明確授權及來源 hash 驗證通過後，於隔離的 ST-LINK Session 執行。
st-flash --freq=100 write plasma-blue-pill-cdc.bin 0x08000000

# 3. 寫入後另一條命令、獨立讀回與位元組核對
st-flash --freq=100 read round-02-readback.bin 0x08000000 18768
sha256sum plasma-blue-pill-cdc.bin round-02-readback.bin
cmp -s plasma-blue-pill-cdc.bin round-02-readback.bin
```

- 此實驗固件 **恰為 18,768 bytes**，SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`。上述 read 的 `18768` 和檔名只對應**歷史實驗**，**不得複製到不同大小／不同 SHA 的新韌體**。
- 歷史三輪都顯示寫入 19 pages，`st-flash write` Exit 0；各自使用新的讀回檔案，實際讀回大小及 SHA 與**當輪輸入的 BIN** 相同。寫入的 Exit 0 **不能取代獨立 Readback**。
- `--freq=100` 是實際命令參數，當時工具訊息表示選用 **50 kHz**；但 LA2016 5 MHz 採樣中的主模態 SWCLK 週期約 10 µs（約 100 kHz）。這個差異**尚未被校準或解決**，不可將該資料寫為精確的時序合格證據。
- 現場若要燒錄新的 PLASMA BIN，先獨立計算來源 SHA256、使用實際檔案大小作為讀回長度，並在擦寫前確認是否必須保存現有 Flash。保存的原始 64 KiB Flash 備份並未放入 Git。
- `st-flash reset` 曾在歷史流程中回傳 Exit 0，USB 也曾重新列舉；**但程式同時警告 `NRST is not connected`**。因此不能將 Reset 的返回碼解讀為已證明 NRST 實體腳位動作。沒有新的明確授權時，不自動執行 Reset。

## 3. LA2016 搭配 ST-LINK 的被動抓波形

參考已成功保存的 [三輪 Golden Reference](../evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md)，其原始 `.sr` 不可覆寫。執行本段前，**先直接執行 [LA2016 工具手冊](la2016-tool-operations.md)「受控初始化」內的 Python/sysfs 動態偵測命令**，由 Codex 產生當次 `LA_CONN`；不要手動提供 USB Path、Bus/Device 編號或複製歷史值。若非唯一裝置、權限不足或裝置遭占用，必須停止而不是任選。

```bash
# 設定為先前已驗證的 AppImage 絕對路徑
SIGROK_APPIMAGE=/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage

# 先執行 la2016-tool-operations.md 的受控初始化：
# Codex 已動態查明 LA_CONN 和現有可讀的韌體資源路徑，不要手動填或覆蓋。
: "${LA_CONN:?Run LA2016 live USB discovery first}"
: "${SIGROK_FIRMWARE_PATH:?Run LA2016 firmware discovery first}"
: "${OUT:?Set a fresh output .sr path first}"

sha256sum "$SIGROK_APPIMAGE"
# LA_CONN 由當次 sysfs 偵測產生，絕不使用上次成功的 bus.device。
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 3 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config samplerate=5m \
  --channels CH0,CH1,CH2 \
  --samples 50000000 \
  --output-file "$OUT"
```

此命令來源是 2026-10-23 三輪 Program／Verify 的受控 `*-sanitized.json` 紀錄。抓取窗口長度 50,000,000 samples / 5 MHz = **10 seconds**；需與實際 ST-LINK 命令時間重疊才可聲稱抓到該操作的訊號。**不要**在這個實驗中開啟 LA2016 PWM1，且不可同時讓 Z2 與 ST-LINK 驅動目標。

如果發生 `Failed to open resource 'kingst-la-01a2.fw'`，先核對成功的 `SIGROK_FIRMWARE_PATH`、受控資源檔案、AppImage SHA、可讀權限與 Driver 啟動環境；不能直接歸因於 LA2016 損壞或 FPGA SWD IP。可參考 [2026-10-16 實測 LA2016 啟動環境](../evidence/la2016-pwm-loopback/2026-10-16/README.md)。修復未驗證前禁止報告 `CAPTURE_PASS`。

## 4. 可比對的 SWD 成功基準與驗收邊界

- 成功 ST-LINK SWD Trace 觀察到 Line Reset、JTAG→SWD、DP IDCODE Request、ACK `OK`、DPIDR `0x1BA01477`，以及後續 AP 傳輸中的部分 `WAIT`。這些都在各輪 `*-decode.txt` 中有實際證據。
- 用 Z2 失敗波形逐項對照 SWCLK 是否活動、SWD 請求位元與方向、Turnaround、3-bit ACK、32-bit 資料與 Parity。**首先報告第一個具證據的不一致，才決定需不需要改 OpenOCD、WordPort Bridge 或 FPGA IP。**
- Sigrok 的解碼器在原始 Golden Reference **沒有獨立標註每一次 Turnaround**，而且它的註解不能代表每一個 SWD 位元都已完美涵蓋。數位 LA 不能證明類比訊號品質。
- 驗證現有封存證據（不接 USB、不操作 DUT）：

```bash
python3 docs/evidence/stlink-stm32f103-swd-reference/2026-10-23/verify.py
```

## 5. 來源及不可越界的事項

- [2026-10-23 既有實機證據](../evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md)、[Round 2 Program 記錄](../evidence/stlink-stm32f103-swd-reference/2026-10-23/round-02-program-sanitized.json)、[Round 2 Readback 記錄](../evidence/stlink-stm32f103-swd-reference/2026-10-23/round-02-verify-sanitized.json)、[OpenOCD Target Voltage](../evidence/stlink-stm32f103-swd-reference/2026-10-23/round-02-voltage-sanitized.log)。
- **這是一份工具手冊及歷史實測契約，不是新的一次實機驗收。** 寫入操作必須有當次明確授權；未確認操作排他權、供電／Flash geometry、備份或韌體來源時停止。
- ST-LINK Golden Reference 的實測成功，只證明 ST-LINK 控制這顆 DUT 類型的能力，**不代表 Z2 OpenOCD／WordPort／FPGA SWD 已成功**。`RUNNER_SUCCESS` 與 `HARDWARE_PASS` 必須分開。
