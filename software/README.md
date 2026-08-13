# Plasma Software

Software 依執行環境與技術棧分成 Python 控制層及 React Web Console：

```text
software/
├── python/   # Plasma control plane v0.3.1 / protocol v3.1
└── web/      # Plasma Programmer Console v0.1.0
```

## Python

`python/` 包含 `plasma_core`、`plasma_server`、`plasma_client`、
`plasma_handlers`、`plasma_interfaces` 與 `plasma_web`。目前可使用 Mock
驗證 1～8 通道排程，Prototype 預設只啟用 CH0、CH1。

```bash
cd software/python
python3 -m unittest discover -s tests -v
```

目前 REST Gateway 使用 Python standard library，Web 已可經由 Gateway 與 Plasma
v3.1 TCP Server 操作 `MockInterface`。尚未切換到計畫中的 FastAPI/WebSocket；
OpenOCD、STM32F103C8T6、PYNQ-Z2/FPGA 與雙通道實機燒錄也尚未驗證。

## Web

`web/` 使用 React、TypeScript、Next.js/Vinext，提供八通道監看介面；
Prototype 中只有 CH0、CH1 可操作。Web 會提交工作到 `python/plasma_web` REST
Gateway，以 500 ms 輪詢真實的 channel/job 狀態，並可向 Python 送出取消要求。

```bash
cd software/web
npm run install:ci
npm run lint
npm test
```

目前畫面成功代表 Python Job Manager 與 `MockInterface` 流程成功，不代表真實硬體
燒錄成功；仍須完成 Z2、FPGA/OpenOCD 與 target 實機整合測試。
