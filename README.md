# Plasma

Plasma 是以 PYNQ-Z2（Z2）為開發平台的多通道 IC 燒錄系統。

目前的第一階段先建立可重建的 FPGA PL 專案結構，後續將逐步加入
2-channel prototype、Python/FastAPI 後端及 React/TypeScript Web Console。

## 目前目錄

- `pl/`：Zynq Programmable Logic 的 RTL、constraints、模擬與 Vivado 建置腳本。
- `docs/`：系統架構、register map、硬體與測試文件（後續階段加入）。
- `software/`：Python 與 Web 軟體（後續階段加入）。

PL 的使用方式請參考 [`pl/README.md`](pl/README.md)。
