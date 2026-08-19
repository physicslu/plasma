# Plasma Software

Software 依執行環境與技術棧分成 Python control plane 與 React Web Console：

```text
software/
├── python/   # PPU control plane + optional read-only Plasma Manager / Protocol v3.2
└── web/      # Plasma PPU Console
```

Canonical domain hierarchy：

```text
Facility -> PPU -> Site
```

Canonical Site identity 是 one-based：`SITE 1 .. SITE N`。目前 prototype 預設啟用 SITE 1、SITE 2，軟體可配置 1～8 Sites。

## Python

`python/` 包含 `plasma_core`、`plasma_server`、`plasma_client`、`plasma_handlers`、`plasma_interfaces`、`plasma_web` 與 optional `plasma_manager`。

```bash
cd software/python
python -m pip install -e '.[dev]'
python -m pytest -q
```

PPU-local canonical path：

```text
Plasma Web REST Gateway
        |
        | Protocol v3.2 / PLASMA32
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
Interface / Handler
```

Optional fleet path：

```text
Plasma Manager
    |
    +--> PPU A Plasma Web REST Gateway
    +--> PPU B Plasma Web REST Gateway
    +--> ...
```

`plasma_manager` 第一版是 read-only fleet control plane：手動設定 PPU Gateway endpoint，獨立讀取每台 PPU 的 liveness、readiness、canonical node identity 與 Site status。Manager failure 不得影響 PPU 本地執行；單一 PPU failure 也不得讓其他 PPU 的 fleet snapshot 消失。

Protocol v3.2 使用 one-based `site_id = 1..N`。Server 暫時保留 Protocol v3.1 compatibility adapter，把 zero-based `channel_id` 明確映射到 one-based Site；新的 domain / REST / CLI / Web request 不應再使用 `channel_id`。

Plasma Web REST Gateway 目前使用 Python standard-library `ThreadingHTTPServer`。它不是 FastAPI，也沒有使用 WebSocket；Web 以 REST polling 取得狀態。

## Web

`web/` 使用 React、TypeScript、Next.js/Vinext 與 Vite tooling，提供 Plasma PPU Console。UI topology 從 canonical `/api/status` 的 `ppu + sites` 動態建立，而不是固定假設八個通道。

Web 會提交 one-based `site_id` 工作到 Plasma Web REST Gateway，並輪詢真實 Site / Job state。Batch operation 可對選定 Sites 並行執行 Erase / Program / Verify / Read；不同 Site 的 pipeline 必須保持獨立。

目前 repository **尚未實作 Fleet Web UI**；不要把 Plasma PPU Console 當成多 PPU Manager UI。

```bash
cd software/web
npm run install:ci
npm run lint
npm test
npm run validate:artifact
```

Browser E2E 與 Visual Regression 位於 `software/web/e2e/`，目前 deterministic baseline 使用 SITE 1..N 的 canonical UI。

## Validation boundary

目前 software / Mock 測試成功代表 control-flow、protocol、Site scheduling、Manager aggregation 與 Web behavior 通過相應測試；不代表 Z2、FPGA/OpenOCD、STM32F103C8T6 或其他 real target 已完成實機燒錄驗證，也不代表 Manager 已完成 integration-host production deployment。

詳細 Python contract 請參考 [`python/README.md`](python/README.md)、[`python/docs/protocol.md`](python/docs/protocol.md) 與 [`../docs/architecture/manager-readonly-fleet-aggregation.md`](../docs/architecture/manager-readonly-fleet-aggregation.md)。
