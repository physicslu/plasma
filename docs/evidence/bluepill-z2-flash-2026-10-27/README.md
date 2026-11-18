# Blue Pill SWD / Flash / CDC 實測，2026-10-27

本目錄保存 2026-10-27 實體實驗的程式、FPGA Image/Manifest、CDC 參考韌體、LA2016 波形及執行回執。實際硬體執行時的 `main` 為 `c37fbb6011c1073c5ec0146633f538a14f4135b9`；本證據 PR 從較新的 `main` `39e313b7d` 建立。執行路徑為 **Path 3**：SWPC Codex 透過既有 SSH/sudo 路徑協調 Z2；所有真實 OpenOCD 及 UNIX WordPort/Remote Bitbang Bridge 均在 **Z2 PS** 執行，SWPC 僅執行被動 LA2016 擷取與 USB CDC 觀測。這次沒有 Dispatcher Run/Job ID。

## 環境與資產

| 項目 | 當時觀測或檔案 |
| --- | --- |
| Z2 Boot ID | `4cefdc0c-f586-4d19-b126-1d8e1108c8f1` |
| FPGA Manager | `operating`；沿用已載入 Image，沒有重新下載 |
| 實際 Image | [plasma-bluepill-swd-65dca783.bin](fpga/plasma-bluepill-swd-65dca783.bin)，SHA256 `bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1` |
| 配對 Manifest | [image-manifest.json](fpga/image-manifest.json)，SHA256 `5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98` |
| Golden recovery | Z2 `base.bin`，SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`；本次沒有 Restore |
| Root source pin | `55f6db3bc5fa866135e5a9070175928d044e53ce` |
| CDC 參考韌體 | [plasma-blue-pill-cdc.bin](firmware/plasma-blue-pill-cdc.bin)，18,768 bytes，SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` |
| OpenOCD | Z2 PS `0.12.0+dev 5088db4c9`；`target/stm32f1x.cfg` SHA256 `bd086fbcb18aaed8839f844be4a8abfa6c284b776e05c8e7e8f1883d6686d7fe` |

Image/Manifest 是本次實際核對的配對資產；Manifest 或檔案雜湊本身不能替代目前 FPGA 載入與 DUT 量測證據。波形 CH2 是 Z2 3.3 V **數位**參考；這不是類比電壓量測。接線與共地依實驗時 owner 確認的狀態；此紀錄不宣稱重新完成歐姆連續性量測。

## 實驗步驟與結果

1. **Step 1，環境與 Identity。** 查核 Boot ID、FPGA Manager、Image/Manifest、Golden、Root pin、Owner/MMIO 與 LA。首次 Identity 嘗試因未釘選 Python bytecode 被 Root Guard 拒絕：`PATH2_UNPINNED_BYTECODE_DENIED`。隔離三個 `.pyc` 後再執行，`IDENTITY_PASS`；三次 MMIO 讀、零次寫；沒有重新載入 FPGA。該 Root Guard 事件不能算作初次 PASS。[Step 1–2 原始結果紀錄](receipts/step12-result.md)。
2. **Step 2，受保護暫存器診斷。** 在既有硬體鎖與 MMIO lease 內，向 `DRIVE 0x40008008` 依序寫 `0x02 → 0x03 → 0x02`；每次寫後做 barrier 再讀 `SAMPLE 0x4000800C`。讀值 `0x09 → 0x0B → 0x09`，SWCLK bit 1 為 `0 → 1 → 0`，SWDIO 輸出使能 bit 2 保持 0。合計七次讀、三次寫，最後為 Low/Hi-Z。
3. **Step 3，同步 LA。** 先啟動 LA2016 再觸發 Step 2 動作。[step3-swclk.sr](waveforms/step3-swclk.sr) 有 30,002,381 samples，1 MHz；CH0/PmodBB P1 於 sample `5,164,661` 和 `6,165,135` 出現兩個邊緣，高電平維持 1.000474 秒。CH1/SWDIO 無邊緣；CH3 第二支 P1 探棒平坦，保留為探棒接觸/位置的未解診斷。詳見 [回執](receipts/step3-capture-report.json)及[分析](receipts/step3-analysis.json)。
4. **Step 4，依證據判定。** CH0 已觀察到要求的實體 SWCLK，內部暫存器也符合；沒有證據支持改 RTL、時序或 OpenOCD 配置，因此沒有這些修正，也沒有動到實體接線。
5. **Step 5，真實 DPIDR。** Z2 PS OpenOCD `init; shutdown` 退出碼 0，日誌含 `SWD DPIDR 0x1ba01477`。Bridge 退出碼 0，2,969 Remote Bitbang bytes、327 MMIO reads、2,551 writes。[step5-dpidr.sr](waveforms/step5-dpidr.sr) 有 100,001,601 samples，5 MHz；CH0 2,524 邊緣、CH1 252 邊緣。只做一次 DPIDR，沒有 Flash 操作。詳見[回執](receipts/step5-capture-report.json)及[分析](receipts/step5-analysis.json)。
6. **Flash 探測及候選頁選擇。** Z2 PS OpenOCD 讀得 STM32F1 device ID `0x20036410`、Flash 64 KiB。先讀最後一頁 `0x0800FC00` 1 KiB，發現 1,020 bytes 非 `0xFF`，因此**沒有擦除最後一頁**。再讀 page 18 `0x08004800` 1 KiB，SHA256 `b2206d042efe720c207c3a1b2eb1827eea2d480fa5c36efddad963708c9d38c6`，與已知 CDC 韌體相同；其中前 336 bytes 為資料，餘下 688 bytes 為 `0xFF`。
7. **Erase、Program、Verify。** 在一個 Z2 PS OpenOCD session 執行 `flash erase_address 0x08004800 0x400`、`flash write_image` 原本 336 bytes 至 `0x08004800`、`flash verify_image`。OpenOCD 與 Bridge 退出碼均為 0；Bridge 計 94,583 wire bytes、13,285 MMIO reads、75,813 writes。[操作回執](receipts/page18-program-report.json)及[波形](waveforms/page18-program.sr)。OpenOCD 沒有逐命令列印擦除/寫入位元組數；不能將 session 結束碼當作獨立的擦除量測。沒有 mass erase 或整片韌體替換。
8. **獨立 Readback。** 全新 Z2 PS OpenOCD/Bridge session 再讀 page 18 的 1,024 bytes；與寫入前備份及韌體參考頁逐位元組相同，SHA256 仍為 `b2206d042efe720c207c3a1b2eb1827eea2d480fa5c36efddad963708c9d38c6`。[讀回回執](receipts/page18-readback-report.json)及[波形](waveforms/page18-readback.sr)。
9. **USB CDC Heartbeat 及 SWD reset。** 燒錄前穩定 uptime 為 `85,158,369–85,164,369 ms`。燒錄後立即讀 CDC 只有一筆舊緩衝訊息，沒有連續 heartbeat；不能視為當時已重啟。依 owner 指示，Z2 PS OpenOCD 執行一次 `reset run`，退出碼 0 且同步擷取[波形](waveforms/reset.sr)。其後六秒 USB CDC 收到 14 筆 heartbeat；穩定 uptime 為 `22,742–28,742 ms`，約每 500 ms 遞增。每次 CDC 讀取的第一筆均為舊緩衝資料，沒有作為 uptime 基準。詳見 [reset 回執](receipts/reset-report.json)、[燒錄前](receipts/cdc-before.json)、[燒錄後立即](receipts/cdc-after.json)、[reset 後](receipts/cdc-after_reset.json)。

## SWD CLOCK 實測

[clock-measurement.json](receipts/clock-measurement.json) 由 5 MHz LA 波形的相鄰 CH0 上升沿計算；page-18 Erase/Program/Verify 階段共 37,229 個上升沿。最常見週期 **1,385 samples = 277 µs ≈ 3,610 Hz**；週期中位數 1,396 samples ≈ 3,582 Hz。因此這次實際 SWD CLOCK 典型值約 **3.6 kHz**。這是 Remote Bitbang/WordPort 加上 PS 執行時序的實測值，並非 OpenOCD `adapter speed` 設定值；交易間的停頓使較長週期也存在。可用 [measure_clock.py](scripts/measure_clock.py) 重算。

## 波形、隱私及復現

[waveforms](waveforms) 含 Step 3/5 及 Flash probe、page-18 前讀、erase/program/verify、獨立讀回、SWD reset 的原始 `.sr`。對應樣本率、邊緣數及來源 SHA 見 [wave-analysis.json](receipts/wave-analysis.json)；CH0/CH1 活動符合 SWCLK/SWDIO，CH2 數位高，CH3 仍平坦。最後一頁讀取的原始 `.sr` 可能編碼未知 Flash 內容，**沒有公開**；發布的 [last-page-read-clock-only.sr](waveforms/last-page-read-clock-only.sr) 僅清除 CH1/SWDIO 位元，保留 CH0/CH2/CH3。原始波形 SHA256 為 `93ba903a2f1a733a4d7e68ff502d035aa6b68f4ee0e218238d3669aa1ac9bbf8`；清除後 SHA256 為 `96dcbcb8d4b776931659bd9d610786e3c3f903226715b9ce4e10d4b6eae0e410`。原始最後一頁 1 KiB 備份亦只留在本機 `.work`，沒有進入 PR。`scripts/` 保留本次執行及分析程式，私有 SSH 憑證及密碼不在此包中。

執行 `python3 docs/evidence/bluepill-z2-flash-2026-10-27/verify.py` 可離線核對檔案 SHA、波形、參考頁及關鍵回執。本驗證只檢查封存資料，不能重新證明目前硬體狀態。完成後的 Z2 Boot ID、Image/Manifest/Golden 不變，FPGA Manager `operating`；`/dev/mem`、`/dev/uio1` 已釋放，OpenOCD/Bridge PID 與 UNIX socket 已清理。FPGA Image 依既有 Keep Loaded 規則留在 PL。
