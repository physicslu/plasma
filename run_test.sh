#!/bin/bash

# === 一鍵測試 Plasma Server + CLI ===

# 設定參數
SERVER_LOG="log/server_test.log"
SERVER_PORT=9000
MAP_PATH="server/handlers/maps/cc2340r5_map.json"
BIN_PATH="testfile/firmware.bin"

echo "📡 啟動 Plasma Server（埠號 $SERVER_PORT）..."
PYTHONPATH=. python3 server/plasma_server_async.py > "$SERVER_LOG" 2>&1 &

SERVER_PID=$!
echo "🧠 Server PID: $SERVER_PID"

# 等待 server 完全啟動（可視需求調整）
sleep 2

echo "🚀 執行 CLI 傳送..."
PYTHONPATH=. python3 client/plasma_cli.py \
  --interface tcp \
  --host 127.0.0.1 \
  --port $SERVER_PORT \
  --map $MAP_PATH \
  --file $BIN_PATH \
  --debug

echo ""
echo "🧾 Server Log Summary:"
tail -n 10 "$SERVER_LOG"

# 停止 server
echo ""
echo "🛑 結束 Server"
kill $SERVER_PID
wait $SERVER_PID 2>/dev/null

echo "✅ 測試完成"

