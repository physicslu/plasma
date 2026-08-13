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

目前 REST Gateway 使用 Python standard library，尚未切換到計畫中的
FastAPI。OpenOCD、STM32F103C8T6、PYNQ-Z2/FPGA 與雙通道實機燒錄也尚未驗證。

## Web

`web/` 使用 React、TypeScript、Next.js/Vinext，提供八通道監看介面；
Prototype 中只有 CH0、CH1 可操作。現階段操作流程仍由瀏覽器內的 Mock timer
模擬，尚未接上 `python/plasma_web` REST Gateway。

```bash
cd software/web
npm run install:ci
npm run lint
npm test
```

不要把畫面上的成功狀態視為真實硬體燒錄成功；必須等 Web API 與 Z2 實機整合
完成後，才可使用真正的 Job 狀態與硬體結果。
