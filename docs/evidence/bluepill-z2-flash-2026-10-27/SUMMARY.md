# 實驗摘要

2026-10-27 使用 PYNQ-Z2 PS 上的 OpenOCD 與 WordPort Bridge，經已載入的 PL SWD Image，完成 Blue Pill 真實 DPIDR 讀取（`0x1ba01477`）。LA2016 在對應擷取窗內觀察到實體 SWCLK/SWDIO；SWCLK 在後續 page-18 Flash 操作期間典型實測約 **3.6 kHz**。

Flash 實驗先讀取並避開含未知資料的最後一頁，再選擇與已知 CDC 韌體一致的 page 18：於 `0x08004800` 擦除 1 KiB、寫回原本的 336 bytes、驗證，並用獨立新 session 讀回整頁，結果逐位元組一致。這是同內容重寫測試，沒有 mass erase 或整片韌體替換。

燒錄後立即讀 USB CDC 未觀察到連續 heartbeat。依指示執行 SWD `reset run` 後，六秒內收到 14 筆 heartbeat，穩定 uptime 從燒錄前約 85,158 秒降至 reset 後約 23 秒，證實 MCU 重啟並繼續從 Flash 執行 CDC 韌體。燒錄本身不能被視為已觸發 reset。

FPGA 沿用原 Image，最後保持載入；硬體鎖及 MMIO 資源已釋放。LA 的 CH3 第二探棒保持平坦，仍需人工檢查探棒接觸/位置。最後一頁含未知 Flash 資料，其原始內容與 SWDIO 波形沒有公開；此目錄提供保留時鐘的清除版波形及來源雜湊。
