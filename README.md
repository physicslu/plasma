# Plasma

Plasma 是一個多通道模擬燒錄平台，支援抽換式通訊介面（TCP/USB），可模擬多通道 IC 燒錄流程，並依照 map.json 執行分段燒錄與自定義處理。

## 🧩 專案特色

- 多通道燒錄模擬（目前支援 8 通道）
- 支援分離階段：/verify、/erase、/program
- 支援 TCP / USB（WinUSB）通訊抽換
- 支援 map.json 指定燒錄位址與順序
- 支援每個 IC 模組自定義區段處理器與檔案預處理


## 🚀 使用方式

### 啟動 Server
```bash
python3 server/plasma_server_async.py
```

### 使用 CLI 傳送燒錄資料
```bash
python3 client/plasma_cli.py --file firmware.bin --interface tcp
```

## 🧪 測試
使用 pytest 進行自動測試：
```bash
pytest tests/
```

---

© 2025 physicslu. All rights reserved.
