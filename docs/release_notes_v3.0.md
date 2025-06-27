# Plasma v3.0 - 發佈紀錄

發佈日期：2025-06-27

---

## ✅ 主要更新項目

- [x] 支援 map.json 自定義多區段 handler 分派
- [x] 加入 handler_map 設計，每顆 IC 可自定義區段邏輯
- [x] CLI 傳輸協定升級為 MAPSIZE/BINLEN header 明確格式
- [x] Server 支援非同步並行接收與錯誤回報
- [x] 預設提供 `default`, `bootloader`, `otp` handler
- [x] IC 模組支援 `preprocess_file()` 客製處理
- [x] Server 改為單一目錄 `server/`，移除 `server_v3`

---

## 🚀 對應檔案結構調整

```
server/
 ├── handlers/
 │   ├── ic_cc2340r5_handler.py
 │   ├── maps/
 │   │   └── cc2340r5_map.json
 │   └── section_handlers.py
 ├── utils/
 │   └── map_parser.py
 ├── plasma_server_async.py
 └── session_manager.py
```

---

## 🧪 測試建議指令

```bash
python3 client/plasma_cli.py \
  --interface tcp \
  --host 127.0.0.1 \
  --port 9000 \
  --map server/handlers/maps/cc2340r5_map.json \
  --file testfile/firmware.bin \
  --debug
```
