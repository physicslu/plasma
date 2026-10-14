# Socket Board Identity / Usage / Presence — Design Notes

> **Status:** Plan（需求與方向紀錄，尚非硬體原理圖或已實作功能）
> **Date:** 2026-10-14
> **Related:** [FPGA Bitstream Identity / Programming Preflight](fpga-bitstream-identity-lifecycle-v1.md)、[ADR-0003](../adr/0003-fpga-bitstream-identity-preflight.md)

## 已確認的產品需求

- 一個 **Site 最多安裝一片可更換的 Socket Board**；每片 Socket Board **只有一個 IC Socket**。第一代雙 Site PPU 可安裝一至兩片，個別 Site 沒有 Socket Board 時必須阻止該 Site 進入燒錄。
- **Site ID**（Site 1、Site 2）由 PPU 定義，不因換板改變；**Socket Board ID** 和使用履歷隨實體板子移動。需建立可變動的 Site → Socket Board 對應。
- 每片 Socket Board 需要非揮發性儲存（目前以 **I²C EEPROM** 為需求基線；I²C FRAM 可在耐久性評估時比較），至少保存：資料結構版本、唯一 Board ID、Board Type / Revision、適用 Socket / package、使用計數與資料完整性資訊。
- 使用次數有**兩個不同目的**：① IC Socket 的**機械壽命**；② **燒錄統計**。不得將一次成功燒錄等同一次機械插拔。
- Socket Board 必須能偵測 **IC 是否在 Socket 中**；這項 IC-present 訊號與 **Socket-Board-present**（板子是否插在 Site）是不同的狀態，不得混為一談。
- IC 未確認存在、板子識別失敗、Socket 與 ICPN/Profile 不相容、機械壽命超過已核准門檻或電氣 preflight 不通過時，Site 預設不可啟動危險的供電/燒錄操作（fail closed）。

## 暫定管理介面與 PCB 預留

- Socket Board 管理功能優先由 **Zynq PS / Linux** 執行，避免依賴會被切換的 FPGA Bitstream。優先檢查 SoM 是否可用 PS MIO I²C；若不可行，再評估固定 EMIO 管理路徑或其他不會因重配置失效的設計。
- 每 Site 的板對板連接器至少評估預留：`MGMT_SDA`、`MGMT_SCL`、`MGMT_VCC`、`GND`、`BOARD_PRESENT`、`IC_PRESENT`；`EEPROM_WP`、`SOCKET_CYCLE_EVENT` 由選定的 Socket / Sensor 方案決定是否需要。
- 管理電源須與 DUT 可變的燒錄電源隔離或妥善隔開，確保在 DUT 未供電時能安全讀取 Board ID、檢查 presence。**不能假設 I²C 腳位直接接入 PL 是必要條件。**
- 多 Site 可評估上游 PS I²C → I²C Multiplexer → 個別 Socket Board，支援相同 EEPROM 位址與隔離。但 MIO pinout、MUX topology、上拉電阻、level shifting、hot-plug 保護與管理電源電壓都需等待正式 SoM/PCB/EEPROM datasheet 驗證，**尚未定案**。

## 兩種計數器與 IC 偵測證據

| 機制 | 資料／事件 | 不能宣稱的事情 |
|---|---|---|
| Mechanical cycle counter | 可觀測 Socket 開合、夾持或插拔事件；事件與抗彈跳需定義 | 沒有感測器時，不得用燒錄次數冒充實測機械週期 |
| Programming counters | `attempt_count`（真正開始燒錄嘗試）、`success_count`（依定義完成驗證）及必要故障統計 | 不能以 success 代表 Socket 沒有磨耗 |
| Socket Board present | Site 接頭上的板存在狀態、EEPROM 身分與插拔映射 | 有板不代表有 IC |
| IC present | 適合目標 Socket 機構的機械/光學/電氣 sensing，並有可觀測的可信度與故障處理 | SWD ACK 或 IC ID 讀取失敗不能直接判定「沒有 IC」；Presence 也不能取代接觸可靠性檢查 |

- Sensor 實作需等 **Socket 類型、可用空間與 IC package** 確定後才選；不同封裝/Socket 的 IC presence 偵測方法可能不同。對無法可靠自動偵測的類型，需明確標示 `unknown`、拒絕無人值守自動操作或制定另外的受控程序，不能假回報 `present`。
- EEPROM/FRAM 更新要能處理斷電、磨耗及損毀：資料格式版本、序列/交易編號、CRC/完整性檢查與冗餘紀錄是候選基線；實際 endurance、回復策略和計數語義應在器件選定後測試。
- `Socket Board UUID` 為板子身分；可偵測 IC presence **不代表能辨識 IC 的真實料號**。選定 ICPN、Board/Socket 相容性、實際電子識別須分別驗證。

## 後續工作／尚未定案

這份文件僅**記錄已確認需求與介面預留原則**，不新增目前 PR 的 Socket Board RTL、PCB、Linux driver 或 Console API。未決項：實體 Socket 規格與開合感測器、IC presence sensor、安全供電/電平、EEPROM vs FRAM、MIO/EMIO routing、計數時點、寫入壽命、可熱插拔策略、供應鏈身分驗證與 HIL 驗收。

在實際產品流程中，Socket Board ID / Presence / Usage preflight 要先於受控 DUT power、FPGA 能力確認及 Programming；若實作順序需變動，仍須確保所有安全條件在 Program 前通過。
