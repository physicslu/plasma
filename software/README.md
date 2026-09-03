# Plasma Software

Software 依執行環境與技術棧分成 Python control plane 與 React Web Console：

```text
software/
├── python/   # PPU control plane + optional read-only Plasma Manager / Protocol v3.3
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
Plasma Gateway
        |
        | Plasma Gateway API / Web REST v3 Programming Asset boundary
        | normalize to execution Image
        | Protocol v3.3 / PLASMA33
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
    +--> PPU A Plasma Gateway
    +--> PPU B Plasma Gateway
    +--> ...
```

`plasma_manager` 是 fleet control plane：Manager registry 中的 `endpoint` 代表每台 PPU 的 **Plasma Gateway Endpoint**，例如 `http://192.168.2.99:18080`。Manager 讀取每台 PPU 的 liveness、readiness、canonical node identity 與 Site status；單一 PPU failure 不得讓其他 PPU 的 fleet snapshot 消失。

Protocol v3.3 使用 one-based `site_id = 1..N`。目前 development runtime 不維護 retired Programmer/Channel compatibility adapter；current code/config/REST/wire 只有 Facility / PPU / Site canonical model。

Plasma Gateway 使用 Python standard-library `ThreadingHTTPServer`。它不是 FastAPI，也沒有使用 WebSocket；Web 以 REST polling 取得狀態。既有 Python package/module 名稱 `plasma_web` 與 service name `plasma-web.service` 是 implementation identifiers，不等於 operator-facing component name。

## Programming data boundary

```text
Programming Asset      # REST/source input
        |
        v
Parser / normalizer
        |
        v
Normalized Image       # Protocol/execution data
```

Programming Asset types可擴充 Image、Key、Option、Serial Number、Calibration。Programming Recipe 是 control-plane instruction，不屬於 Asset。

## Web

`web/` 使用 React、TypeScript、Next.js/Vinext 與 Vite tooling，提供 Plasma PPU Console。UI topology 從 canonical `/api/status` 的 `ppu + sites` 動態建立，而不是固定假設八個通道。

Web 會提交 one-based `site_id` 工作到 Plasma Gateway API，並輪詢真實 Site / Job state。Batch operation 可對選定 Sites 並行執行 Erase / Program / Verify / Read；不同 Site 的 pipeline 必須保持獨立。

Production Mode 的 `/fleet` Factory Console 已提供多 PPU operator UI；其 topology/observation 可由 optional Manager 與 Plasma Gateway provider 提供，執行命令由 server-owned Batch Runtime 負責。

```bash
cd software/web
npm run install:ci
npm run lint
npm test
npm run validate:artifact
```

Browser E2E 與 Visual Regression 位於 `software/web/e2e/`。

## Terminology boundary

```text
Plasma Gateway          PPU 上的 northbound API service
Plasma Gateway API      該 service 的 REST contract
Plasma Gateway Endpoint 例如 http://192.168.2.99:18080
Default Gateway         Linux eth0 的 Layer-3 next-hop router
```

Network configuration JSON field `gateway` 保留既有 wire schema，但其語意是 **Default Gateway**，不是 Plasma Gateway。

## Validation boundary

software / Mock 測試成功代表 control-flow、Protocol v3.3、Site scheduling、Manager aggregation 與 Web behavior 通過相應測試；不代表 Z2、FPGA/OpenOCD、real target 或 production socket 已完成實機驗證。

詳細 contract 請參考 [`python/README.md`](python/README.md)、[`python/docs/protocol.md`](python/docs/protocol.md) 與 [`../docs/architecture/web-rest-api-contract.md`](../docs/architecture/web-rest-api-contract.md)。
