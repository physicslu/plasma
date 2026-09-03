# Plasma v0.3.3 軟體架構

## 設計基準

軟體支援每台 PPU 配置 1～8 個 **Programming Sites**。Canonical Site ID 從 1 開始；每一個 enabled Site 都擁有自己的 worker、queue、handler 與 interface instance。

PPU-local execution path：

```text
Browser / CLI / Client
        |
        | Plasma Gateway API / Web REST v3 Programming Asset boundary
        | normalize to Image
        v
Plasma Gateway
        |
        | Plasma Protocol v3.3 / PLASMA33 to local execution service
        v
Plasma Server
        |
        v
SiteManager
        |
        +--> SITE 1 Worker -> Handler -> Interface
        +--> SITE 2 Worker -> Handler -> Interface
        +--> ... SITE N
```

Optional fleet path：

```text
Fleet client
    |
    v
plasma_manager
    |
    +--> PPU A Plasma Gateway -> local Plasma Server -> SiteManager
    +--> PPU B Plasma Gateway -> local Plasma Server -> SiteManager
    +--> ...
```

`plasma_manager` 是獨立於 `plasma_server` 的 optional fleet control plane。它只能透過每台 PPU 的 Plasma Gateway API / fleet-facing contract 取得 health、identity 與 Site topology，並透過明確 allowlist 的 managed route 執行核准的 PPU API 操作；不能繞過 PPU boundary 直接呼叫遠端 `SiteManager` / `SiteWorker`。PPU 本地執行不依賴 Manager。

Plasma 仍在開發期，current runtime 只保留 Facility / PPU / Site canonical model；不維護退休的 zero-based Programmer/Channel compatibility adapter。

## 責任邊界

| 模組 | 責任 | 不應負責 |
|---|---|---|
| `plasma_client` | 建立 request、Protocol v3.3 TCP 傳輸、CLI | Site 排程與硬體操作 |
| `plasma_core` | Programming Asset/Image models、errors、config、protocol、log/output | target-specific 指令 |
| `plasma_server` | 連線、Job registry、Site queue/worker、cancel | MCU 燒錄細節、fleet orchestration |
| `plasma_web` | **Plasma Gateway implementation package**；PPU-local REST v3 boundary、Asset validation/normalization、browser-facing API | 跨 PPU scheduling |
| `plasma_manager` | PPU registry、fleet health / identity / Site aggregation、explicit managed routing | PPU-local execution、直接控制 SiteWorker、arbitrary reverse proxy |
| `plasma_handlers` | IC 的獨立 erase、program、verify、read 操作 | TCP、檔案路徑、AXI 位址 |
| `plasma_interfaces` | 實際硬體或 Mock 操作 | Job 排程與跨 Site 策略 |

`plasma_web` 是 compatibility-sensitive Python package 名稱；產品/架構名稱為 **Plasma Gateway**。

## Network terminology boundary

```text
Plasma Gateway          PPU northbound API service
Plasma Gateway API      its REST contract
Plasma Gateway Endpoint service location, e.g. http://192.168.2.99:18080
Default Gateway         Linux eth0 Layer-3 next-hop router
```

PPU network JSON field `gateway` 保留 wire compatibility，但其語意是 **Default Gateway**。

## Programming data boundary

```text
Programming Asset
    |
    | parser / normalizer
    v
Normalized Image
    |
    | Protocol v3.3
    v
PPU execution
```

Asset SHA 是來源/cache identity。Normalized Image SHA 是 Program/Verify execution identity 與共享資源 arbitration authority。Programming Recipe 是 future control-plane instruction，不屬於 Asset。

## Job 生命週期

```text
QUEUED -> RUNNING -> SUCCESS
   |         |----> FAILED
   |         |----> TIMEOUT
   |         |----> CANCELLED
   |----> CANCELLED
restart: QUEUED/RUNNING -> ABORTED
```

Terminal state 不會再被改為另一個結果。Server restart 將不完整 Job 標記為 `aborted`，不會假設 programming 成功，也不會自動重試不確定 target state。

## 進度與取消控制流

CLI/Web 使用非阻塞提交模式。Server 排入 Site queue 後立即回傳 `job_id`，Client 再以短連線輪詢 Job snapshot。Cancel 針對單一 Job/Site，等待 terminal state 後才完成。

```text
Client -> Server: v3.3 submit(site_id=1, wait=false)
Server -> Client: accepted + job_id
Client -> Server: status(job_id)
Server -> Client: site_id + stage + progress
Client -> Server: cancel(job_id)
SiteWorker -> Server: cancelled + safe shutdown
```

目前 PPU transport 採一 request／一 response 的短 TCP connection，保持明確 frame boundary。未來若改 persistent connection，仍必須保持 frame、Job identity 與 payload boundary。

## 並行與隔離

- 每個 Site 一次只執行一個工作。
- 不同 Sites 可以平行執行，彼此不應互相等待。
- 全域 semaphore 依 `max_concurrent_jobs` 限制真正執行數。
- cancel、timeout 與 retry 僅操作該 Job 所屬的 interface。
- 每個 Site 使用獨立 interface instance。
- 真實共用資源限制必須在硬體/Provider 層明確建模，不得偽裝成任意跨 Site serialization。
- Program/Verify 的 PPU-wide active Image lease 以 Normalized Image SHA 為 authority。
- Plasma Manager 對各 PPU 獨立 polling；Manager failure 只影響 fleet visibility/control-plane access，不得停止健康 PPU 的 local execution。

## Identity invariants

```text
SITE 1 == site_id 1
SITE 2 == site_id 2
...
SITE N == site_id N
```

禁止在 canonical code 中建立 SITE 0 或第二套 Site identity namespace。Fleet 層另要求 `ppu_id` 在同一 Manager registry 觀測範圍內保持唯一。

## 資料持久化

PPU 目前使用檔案持久化 Job state、result、audit log 與 read-back output。Canonical Job log 使用 `SITE<n>` 路徑與 `site_id`，read-back binary 使用 `read_SITE<n>_...`。

Plasma Manager 的 last-known observation 可選擇 memory-only 或 SQLite；這是 fleet availability aid，不得成為 PPU execution dependency。

## 下一階段硬體整合順序

1. Z2 上建立單 PPU / deterministic loopback execution path。
2. 驗證 Protocol v3.3、one-based Site routing、Image SHA、cancel 與 progress。
3. 驗證 SITE 1 / SITE 2 真正 parallel，不只是在 Mock 中並行。
4. 定義 Z2 register map、power/reset safety state 與 fault reporting。
5. 再導入 SPI Flash、I2C EEPROM、SWD MCU 等 real target interfaces。
