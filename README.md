# Plasma

Plasma 是以 PYNQ-Z2（Z2）為開發平台的多通道 IC 燒錄系統。Prototype
先啟用 CH0、CH1，軟體與 RTL 架構保留擴充到八通道的能力。

## 目前目錄

- `pl/`：Zynq Programmable Logic 的 RTL、constraints、模擬與 Vivado 建置腳本。
- `docs/`：系統架構、register map、硬體與測試文件（後續階段加入）。
- `software/python/`：Plasma v0.3.1 Python 控制層、TCP Server、CLI、REST Gateway 與測試。
- `software/web/`：React + TypeScript Plasma Programmer Console。

PL 的使用方式請參考 [`pl/README.md`](pl/README.md)。
Software 的版本、限制與測試方式請參考 [`software/README.md`](software/README.md)。
跨電腦的 GitHub、VS Code、Command Line 與 Vivado 工作流程請參考
[`docs/development/multi-machine-development-guide.md`](docs/development/multi-machine-development-guide.md)。
