本說明文件為開發者指引，用於在 Plasma v3.0 中新增一顆自定義 IC 模組，支援多區段 map 與分派 handler。

---

## 1. 建立 handler 模組

在 `server/handlers/` 下新增一個檔案，例如：

```bash
server/handlers/ic_cc2340r5_handler.py

範例如下：
from server.handlers.section_handlers import default_handler, bootloader_handler

async def preprocess_file(raw_data: bytes, map_data: list):
    # 若有特殊轉換，可在此處理
    return raw_data

handler_map = {
    "default": default_handler,
    "bootloader": bootloader_handler,
}

## 2. 設定 map.json 區段檔案

建立對應的區段 map 檔案，例如：
server/handlers/maps/cc2340r5_map.json

內容範例如下
[
  {
    "offset": 0,
    "size": 1024,
    "target": "0x00000000",
    "handler": "default"
  },
  {
    "offset": 1024,
    "size": 1024,
    "target": "0x00001000",
    "handler": "bootloader"
  }
]

## 3. CLI 指令測試

使用 CLI 測試：

python3 client/plasma_cli.py \
  --interface tcp \
  --host 127.0.0.1 \
  --port 9000 \
  --map server/handlers/maps/cc2340r5_map.json \
  --file testfile/firmware.bin \
  --debug

##4. Handler 回傳格式
  每個 handler 應回傳如下格式（dict）：
  return {
    "message": "寫入成功",
    "extra_info": "可選欄位"
}

