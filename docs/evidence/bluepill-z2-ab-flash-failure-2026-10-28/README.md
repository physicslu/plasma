# Blue Pill v0.1/v0.2 Flash 失敗、讀回與不擦除寫回紀錄，2026-10-28

**結果：首次 v0.1 擦除後寫入 FAIL，獨立讀回確認前 19 頁全 `0xFF`；之後在 Owner 指示下，不再預讀或擦除，直接寫回 v0.1，獨立讀回與 CDC heartbeat PASS；v0.2 NOT_RUN。** 本紀錄保存實際觀測與未完成項目，不是 Flash 寫入路徑的通用資格證明。實驗使用 Gate 1 已核准的 Path 3：SWPC Codex 透過既有 SSH/sudo 路徑協調 Z2；即時 OpenOCD 和 UNIX WordPort/Remote Bitbang Bridge 均在 Z2 PS 執行，經已載入的 PL SWD Image 接到 Blue Pill。沒有 Dispatcher Run/Job ID。操作時倉庫 `main` 為 `bd06f4fec8ab8a721401811be3b4dc23d45211d7`。本次沿用 [2026-10-27 已實測的 Z2 路徑](../bluepill-z2-flash-2026-10-27/README.md)；未使用仍為草稿的 PR #1189 雙 Site IP。

## 映像與寫入前狀態

| 項目 | 實際核對或觀測 |
| --- | --- |
| PR #1197 CI 來源 | Run `40534316798`，HEAD `b8bb2dc2392b6a267247357627c9ea5ff46538ef`；下載兩版 BIN 並在 SWPC 核對 SHA256 |
| v0.1 BIN | 18,768 bytes；SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` |
| v0.2 BIN | 62,800 bytes；SHA256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |
| Z2 Boot ID | `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`，與封存前次實驗相同；本次重新讀取 |
| FPGA Image / Manifest | Image SHA256 `bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1`；Manifest SHA256 `5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98` |
| Root / Golden | Root source pin `55f6db3bc5fa866135e5a9070175928d044e53ce`，source check PASS；Golden SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c` |
| Ownership | 寫入前 FPGA Manager `operating`，沒有 OpenOCD/Bridge PID，`/dev/mem` 和 `/dev/uio1` 無占用 |

寫入前 USB CDC 實際觀測到 v0.1 heartbeat：20 筆，排除首筆舊緩衝訊息後序號連續、uptime 每約 500 ms 增加。該輪沒有得到 `ID` 回覆，故只將 heartbeat 部分列為觀測，不列完整 CDC 基線 PASS。沒有把歷史訊息當作燒錄後證據。

## 實際執行順序

1. **第一次完整備份 FAIL，未寫入。** 原版 Bridge 的 `signal.alarm(60)` 在約 4 KiB 時中斷 64 KiB `dump_image`，OpenOCD 隨 socket 斷開而失敗。確認程序及 MMIO 無殘留後，刪除不完整備份。這個 60 秒限制與後續 Flash 寫入錯誤不同。
2. **完整備份 PASS。** 本次單次實驗的 Bridge 副本將匯入路徑固定為原有 Z2 PS 部署目錄、執行上限延長至 3,600 秒，保留 Root/Manifest、owner lock、MMIO lease 等檢查；副本 SHA256 `7b004f49c9626aad8e9efc2fafa5a64e43d099ff238befbe56fb43c1cc964c4b`。Z2 PS OpenOCD/Bridge 均退出 0，讀到 DPIDR `0x1ba01477`、device ID `0x20036410`、64 KiB Flash。讀取 65,536 bytes 後，Z2 與 SWPC 備份 SHA256 均為 `7e41a8b048e8ed67de84d868446d73344f0d09e662c6aea92ae936b18752336e`。備份前 18,768 bytes 與 v0.1 BIN 逐位元組相同。最後一頁有 1,020 bytes 非 `0xFF`，其原始內容未公開。
3. **v0.1 擦寫 FAIL。** 同一個新 Z2 PS OpenOCD session 依序下達 `init; halt; flash probe 0; flash erase_address 0x08000000 0x4c00; flash write_image <v0.1 BIN> 0x08000000 bin; flash verify_image ...; reset run; shutdown`。預定擦除範圍為起始 19 個 1 KiB 頁，沒有 mass erase，也不含最後一頁。OpenOCD 再次認得 DPIDR、device ID 和 64 KiB Flash，接著在第一個寫入位址回報：

   ```text
   Error: timeout waiting for algorithm, a target reset is recommended
   Error: flash write failed just before address 0x8000000
   Error: error writing to flash at address 0x08000000 at offset 0x00000000
   ```

   OpenOCD 退出碼 1；Bridge 退出碼 0，socket 已移除。`flash verify_image` 與 `reset run` 沒有成功回執。當時沒有獨立擦除讀回，故尚不能判定實際改變範圍。
4. **失敗後停寫。** 沒有重試擦寫、reset DUT、燒 v0.2 或操作電源。Z2 唯讀核對顯示 OpenOCD/Bridge 無殘留，MMIO 無占用，FPGA Manager `operating`，Image/Manifest/Root pin/Golden 不變。依 Keep Loaded 規則保留 FPGA Image，沒有 Golden Restore。
5. **Owner 指示後獨立讀回 PASS。** 在同一 Boot ID 和安全前置條件下，另開 Z2 PS OpenOCD/Bridge session，僅執行 `init; halt; flash probe 0; dump_image <current-full.bin> 0x08000000 0x10000; shutdown`；沒有 erase、program、reset 或 resume。OpenOCD 與 Bridge 均退出 0，讀滿 65,536 bytes，DPIDR `0x1ba01477`、device ID `0x20036410`、Flash 64 KiB；Z2 與 SWPC SHA256 均為 `830c9eeffac617953f3a8a6095f946b4796baa054fd0e1e4e4b88419aab13f5e`。與寫入前備份逐位元組比較，**目前 Flash 恰等於「原始備份前 19 頁改為全 `0xFF`，後 45 頁不變」**。變動的 18,580 bytes 全部由非 `0xFF` 變成 `0xFF`，沒有觀測到寫入的新非 `0xFF` 資料。前 19 頁覆蓋 `0x08000000–0x08004BFF`；最後一頁及其 1,020 bytes 非 `0xFF` 資料逐位元組不變。此讀回不匹配 v0.1 或 v0.2 BIN。讀回後再次核對無 OpenOCD/Bridge/MMIO 占用，FPGA Image/Manifest/Root/Golden 不變。

## 不預讀、不擦除的 v0.1 寫回與 LA 擷取

Owner 接著指示只寫前 19 頁、同步使用 LA2016，不再於燒錄前讀取或擦除。執行前重新核對 Z2 Boot/Image/Manifest/Root/Golden 與 owner/MMIO 無占用，並核對已保存的全 `0xFF` 讀回 SHA；這是既有檔案身分核對，沒有重新讀取 DUT Flash。LA2016 使用 SHA256 `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475` 的 Sigrok AppImage、當次唯一 `77a1:01a2` USB 裝置與原生 Driver，被動擷取 CH0–CH3，未開啟 PWM 輸出。

1. LA 原生 session 開始後，Z2 PS OpenOCD 執行 `init; halt; flash probe 0; flash write_image <v0.1 BIN> 0x08000000 bin; flash verify_image <v0.1 BIN> 0x08000000 bin; shutdown`。**沒有 `flash erase_address`、預先 `dump_image` 或 reset**。OpenOCD 與 Bridge 均退出 0；命令退出只證明 session 完成，尚須獨立讀回。
2. LA2016 退出 0，原始 `.sr` SHA256 `66720303e56a9aa2b66c3fd56b3c3817adce7c447399d7147d9c162b8191bca5`，5 MHz、200,002,421 samples，實際邏輯擷取長度 40.0004842 秒。CH0/SWCLK 有 208,878 個邊緣、CH1/SWDIO 有 37,302 個邊緣，CH2/CH3 無邊緣；擷取在 Z2 命令之前啟動，窗內有真實 SWD 活動。40 秒波形**不涵蓋整個約 100 秒的寫入／驗證 session**，也沒有獨立標註第一個 Flash 資料交易，因此不能單靠波形宣稱整片寫入正確。原始 `.sr` 保留在私有 SWPC 工作目錄，不含於本 PR；數位 CH2 HIGH 亦不等於類比電壓合格。
3. 另開全新 Z2 PS OpenOCD/Bridge session，只讀回 `0x08000000` 起 18,768 bytes，未 reset 或 resume。兩個程序均退出 0，讀回檔與 PR #1197 v0.1 BIN 在 Z2 和 SWPC **逐位元組相同**，SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`。此步驗證 v0.1 映像長度，沒有再次全片讀回其餘頁。
4. 獨立讀回後，Z2 PS 執行一次 `reset run`，OpenOCD/Bridge 均退出 0；USB 重新列舉 `CAFE:4001`。其後 9 秒 CDC 取得 20 筆 `HB version=0.1`。排除第一筆舊緩衝資料後，其餘 19 筆序號連續、uptime 每約 500 ms 增加，並收到兩次 `ID PLASMA_BLUE_PILL_CDC/0.1`。第一個 `ID` 查詢附近曾收到一筆 `ERR UNKNOWN_COMMAND`，後兩次 ID 回覆正確；該筆錯誤原因未另診斷。不能把首筆舊緩衝 heartbeat 當作 reset 後 uptime 基準。
5. 最後 Z2 唯讀核對：OpenOCD/Bridge 無殘留、`/dev/mem` 和 `/dev/uio1` 無占用，FPGA Manager `operating`，Image/Manifest/Root pin/Golden 不變。FPGA Image 保持載入，沒有 Golden Restore。沒有進行 v0.2 燒錄。

## 判讀、缺口與恢復風險

故障點是 **OpenOCD 的 STM32 Flash 寫入演算法未完成**。OpenOCD 上游[原始碼](https://www.openocd.org/doc/doxygen/html/target_8c_source.html)在非同步 Flash 寫入的 FIFO 無預期進展時會報相同逾時；這有助於理解訊息，**不足以證明**本次是 DUT RAM 演算法、Z2 WordPort/SWD 時序、電氣狀態或 Flash 控制器的哪一項造成。成功讀取 DPIDR 和完整備份不能證明寫入路徑可用。

第一次失敗的擦除／寫入**沒有同步 LA2016 波形**，PR #1196 歷史波形不能代替；後續不擦除寫回則有上述 LA 擷取。第一次寫入 FAIL 與後續 v0.1 寫回／讀回／CDC PASS 是兩個分開的結果，不可互相覆蓋。v0.2 擦寫、讀回和 heartbeat 均 **NOT_RUN**。本次沒有改 repo 生產程式、沒有 FPGA load、沒有 PR merge 或部署。

寫入前原始備份、失敗後全 `0xFF` 區域的 64 KiB 讀回、v0.1 寫回後 18,768-byte 讀回及 LA 原始 `.sr` 均保留在私有 SWPC `.work/bluepill-ab-20261028/` 或 Z2 暫存目錄，不包含在本 PR。第一次「先擦除再寫入」失敗的根因仍未定；若要重現，應同步被動擷取 LA2016 並保存完整命令與退出回執。此次不擦除寫回在這一顆 DUT 與既有 Z2 Image 上已實測成功，但不自動推廣為 v0.2 或其他目標的寫入資格。
