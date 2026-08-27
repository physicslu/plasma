# Plasma 錯誤碼

| Code | Protocol v3.3 Type | 說明 |
|---|---|---|
| E1001 | INVALID_ARGUMENT | CLI、map、timeout、Site ID 或其他參數錯誤 |
| E1002 | CONFIG_INVALID | YAML 或 Site 設定不合法 |
| E2001 | CONNECTION_FAILED | Client 無法建立連線 |
| E2002 | CONNECTION_TIMEOUT | 連線或 response 等待逾時 |
| E3001 | PROTOCOL_HEADER_INVALID | Magic/header 不合法或 Magic/版本不一致 |
| E3002 | PROTOCOL_INCOMPLETE | 半包或宣告長度不符 |
| E3003 | PROTOCOL_VERSION_UNSUPPORTED | 協定版本不支援 |
| E3004 | PROTOCOL_PAYLOAD_TOO_LARGE | Payload 超過設定上限 |
| E3005 | PROTOCOL_JSON_INVALID | Metadata/map JSON 不合法 |
| E3006 | PROTOCOL_CHECKSUM_MISMATCH | Binary SHA-256 不符 |
| E4001 | SITE_INVALID | one-based Site ID 不存在 |
| E4002 | SITE_DISABLED | Site 存在但已停用 |
| E4003 | SITE_BUSY | Site queue 已滿 |
| E4004 | JOB_NOT_FOUND | Job ID 不存在 |
| E4005 | OPERATION_UNSUPPORTED | 操作不支援 |
| E4006 | DUPLICATE_JOB | Job ID 重複 |
| E4007 | BATCH_NOT_FOUND | Batch ID 不存在 |
| E4008 | BATCH_SITE_FAILURE_THRESHOLD_EXCEEDED | FAULTED Site 數達到 Batch stop threshold |
| E4009 | BATCH_INFRASTRUCTURE_ERROR | Batch runtime、Gateway 或 PPU 通訊基礎設施異常 |
| E4010 | PPU_BUSY | PPU 已由另一個 active execution owner 使用；新 execution 必須 fail closed |
| E5001 | TARGET_NOT_FOUND | 找不到 target（預留實機） |
| E5002 | INTERFACE_FAILURE | OpenOCD／FPGA 介面錯誤，或無法完成安全關閉 |
| E5003 | INTERFACE_NOT_CONFIGURED | 硬體介面尚未配置或實作 |
| E6001 | ERASE_FAILED | 擦除失敗 |
| E6002 | PROGRAM_FAILED | 寫入失敗 |
| E6003 | VERIFY_FAILED | 驗證不一致或失敗 |
| E6004 | READ_FAILED | 讀回失敗 |
| E7001 | OPERATION_TIMEOUT | Job 執行逾時 |
| E7002 | OPERATION_CANCELLED | Job 被取消 |
| E8001 | OUTPUT_WRITE_FAILED | Output/result/log 寫入失敗 |
| E9001 | INTERNAL_ERROR | 未預期的軟體錯誤 |
| E9002 | JOB_ABORTED | Server 重啟時發現未完成 Job |

Protocol v3.3 是唯一 canonical runtime wire contract。Current runtime 使用 canonical Site／Job／Batch／PPU errors；不提供退休的 Channel error aliases。

`PPU_BUSY` 是 control-plane admission conflict，不是 IC programming FAIL。當另一個 execution owner 仍有 active Jobs 時，新 owner 的 Job 必須在建立 Job 前被拒絕。`recoverable=true` 表示 caller 可在 ownership 釋放後重新嘗試，不代表可以越過既有 owner 強制執行。

`recoverable=true` 只表示軟體允許依政策重試，不代表重試必然安全。對於不確定 target 是否已部分寫入的操作，handler 必須先執行明確的復原流程，例如 reset、重新 halt 與完整 erase。

若工作本身完成、但 `safe_shutdown()` 失敗，結果仍必須是 `failed/E5002`；因為系統無法保證該 Site 已回到安全狀態。
