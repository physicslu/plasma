# PLASMA 跨廠牌燒錄預設政策：目標執行與中斷隔離

狀態：2026-10-28 Owner 指定之燒錄流程設計政策。適用所有 Manufacturer、Exact ICPN、Provider 與 Site。**這是預設規範，不代表所有現有 Provider 已完成程式實作或實機資格。**

## 預設要求

任何破壞性 Erase／Program 開始之前，必須讓目標進入**經驗證、不會干擾燒錄演算法的受控狀態**。若目標有可執行韌體與中斷系統，且燒錄期間會在目標 CPU 上執行 Flash Algorithm，**預設必須隔離／遮罩可能中斷演算法的應用程式中斷**；不得預設舊韌體的 NVIC、SysTick、RTOS 中斷狀態安全。

此規則適用所有 IC，但**不能對所有 IC 執行同一個 Cortex-M OpenOCD 指令**。ROM ISP、不同 CPU、外部 SPI Flash 或 EEPROM，必須採用符合該裝置原廠文件及 Provider 行為的等效隔離方法。無 MCU 中斷者須以證據明示 NOT_APPLICABLE；未定義、未驗證或失敗則 BLOCKED，不可靜默略過。例外在既有 Gate 1 審核並留下 Exact ICPN／Provider 來源證據，不新增第三道批准 Gate。

## 標準 Erase／Program 流程

1. 驗證 Exact ICPN、Image/SHA、Geometry、Provider、FPGA／Root、設備所有權、供電及復原條件。
2. 進入經審核的 Programming／Debug／ISP 模式。**Erase 前**建立且實測目標執行及中斷隔離；失敗即停止。
3. 執行核准範圍的 Erase。若 Erase 演算法可能改變核心狀態，**Program 前**重新檢查隔離。
4. Program 期間必須確保隔離策略涵蓋整段關鍵 Flash Algorithm；單靠前後兩次暫存器取樣，不得宣稱全程不中斷。
5. 明確執行 Verify、獨立 Readback/SHA。失敗保留原始 Session 診斷，停止、不自動重試。Reset、Resume、恢復中斷、VCC 操作均依各目標獨立策略，不隱含執行。

注意：Cortex-M 的 maskisr 只涵蓋其支援的可遮罩中斷，不能據此宣稱 NMI、HardFault、DMA、Watchdog 或其他核心已完全隔離。各 Provider 的資格證據須記錄適用範圍、例外、負向測試與實際保護保證。

## STM32F103C8T6 Z2 Site 1 已確認的實機例子

Draft PR #1200 的 OpenOCD 實驗程式在 init; halt 後執行 cortex_m maskisr on，並在 PRE_ERASE 及 PRE_PROGRAM 讀取 DHCSR (0xE000EDF0)，要求 S_HALT(17)、C_MASKINTS(3)、C_HALT(1)、C_DEBUGEN(0)，必要位元遮罩 0x0002000B；若不符合即 Fail Closed。

2026-10-28 操作員提供之 SWPC Run：
SWPC operator-retained private A/B run (2026-10-28)

v0.1→v0.2→v0.1→v0.2 共 4/4 次完整 Program／Readback／Reset／CDC PASS；OpenOCD、Bridge Exit Code 全為 0。四份獨立 Z2 openocd.log 每份皆包含：

    PLASMA_IRQ_MASK_PASS PRE_ERASE 0x0003000B
    PLASMA_IRQ_MASK_PASS PRE_PROGRAM 0x0003000B

合計 8/8 個檢查點 PASS。本次未再觀察到 Flash Algorithm Timeout；但尚不能唯一證明 Root Cause 或全程中斷隔離，也不得宣稱其它 ICPN 已通過驗證。手動 100 次燒錄耐久測試成果尚未納入本紀錄。

## 實作邊界

本次僅記錄跨廠牌預設規範與既有實機證據。未修改執行程式、FPGA、部署設定、現場燒錄或 Catalog 等級。跨 Provider 的資格資料模型、執行時阻擋與負向測試仍須另行實作與驗證。

參考：docs/development/image-agnostic-wordport-path2.md、docs/architecture/ic-support-openocd-plan-executor.md、ADR-0002。
