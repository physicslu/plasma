# Plasma

Plasma 是以 PYNQ-Z2（Z2）為目前硬體開發平台的多 Site IC programming system prototype。
一台實體燒錄設備建模為 **Plasma Programming Unit (PPU)**；每個 PPU 內含 1～8 個可獨立排程與執行工作的 **Programming Sites**。

Canonical domain hierarchy：

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Canonical Site ID 從 **1** 開始，不存在 `SITE 0`。目前 prototype 預設啟用 SITE 1、SITE 2，其餘 Site 依 PPU configuration 決定是否啟用。

## 目前目錄

- `pl/`：Zynq Programmable Logic 的 RTL、constraints、模擬、verification 與 Vivado 建置資產。
- `software/python/`：Plasma PPU control plane、Protocol v3.2 TCP Server、CLI、Plasma Web REST Gateway、optional read-only Plasma Manager 與測試。
- `software/web/`：React + TypeScript Plasma PPU Console。
- `scripts/plasmactl`：integration host 的更新、測試、systemd reconciliation、重啟與服務管理入口。
- `docs/`：architecture、development 與 deployment 文件。

## Current PPU-local software path

```text
Browser / Plasma PPU Console
        |
        | HTTP REST polling
        v
Plasma Web REST Gateway
        |
        | Plasma Protocol v3.2 / PLASMA32
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
MockInterface today; Z2/FPGA/real-target validation is a separate stage
```

PPU 是 autonomous execution node；本地燒錄不依賴 Plasma Manager。

Optional fleet path：

```text
Fleet client
    |
    v
Plasma Manager (read-only registry / aggregation)
    |
    +--> PPU A Plasma Web REST Gateway -> local execution
    +--> PPU B Plasma Web REST Gateway -> local execution
    +--> ...
```

第一版 Plasma Manager 只使用手動設定的 PPU Gateway endpoints 彙整 health、identity 與 Site topology，不提供 job routing、central scheduling、discovery、Fleet Web UI 或 production deployment integration。

目前 Plasma Web REST Gateway 使用 Python standard-library `ThreadingHTTPServer` 與 REST polling；**不是 FastAPI，也沒有使用 WebSocket**。

Protocol v3.2 的 canonical wire identity 是 one-based `site_id = 1..N`。Protocol v3.1 的 zero-based `channel_id` 只保留在明確的 compatibility boundary，不是新程式的 domain contract。

## 文件入口

- Domain / naming / identity：[`docs/architecture/domain-naming-migration.md`](docs/architecture/domain-naming-migration.md)
- Facility / PPU / Site architecture：[`docs/architecture/ppu-facility-sites.md`](docs/architecture/ppu-facility-sites.md)
- Plasma Web REST API contract：[`docs/architecture/web-rest-api-contract.md`](docs/architecture/web-rest-api-contract.md)
- Engineering Programming observability / audit contract：[`docs/architecture/engineering-programming-observability.md`](docs/architecture/engineering-programming-observability.md)
- Optional Manager invariant：[`docs/architecture/manager-optional-control-plane.md`](docs/architecture/manager-optional-control-plane.md)
- Read-only Manager implementation：[`docs/architecture/manager-readonly-fleet-aggregation.md`](docs/architecture/manager-readonly-fleet-aggregation.md)
- Protocol v3.2：[`software/python/docs/protocol.md`](software/python/docs/protocol.md)
- Python software：[`software/python/README.md`](software/python/README.md)
- Web Console：[`software/web/README.md`](software/web/README.md)
- FPGA / PL：[`pl/README.md`](pl/README.md)
- Multi-machine development：[`docs/development/multi-machine-development-guide.md`](docs/development/multi-machine-development-guide.md)
- Integration-host deployment：[`docs/development/swpc-deployment.md`](docs/development/swpc-deployment.md)
- Codex Cloud：[`docs/development/codex-cloud-environment.md`](docs/development/codex-cloud-environment.md)
- Local AI / Cline / Ollama：[`docs/development/local-ai-development-guide.md`](docs/development/local-ai-development-guide.md)

## Validation boundary

Mock、CI、SWPC deployment、Vivado implementation、Z2 runtime 與 real IC programming 是不同的驗證層。任何一層 PASS 都不能被擴大解讀成尚未實際執行的下一層驗證成功。
