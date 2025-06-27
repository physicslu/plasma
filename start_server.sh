#!/bin/bash

echo "[INFO] 啟動模擬燒錄器..."

python3 server/plasma_server_async.py --port 9000 --ic cc2340r5 > log/server_9000.log 2>&1 &
echo "[INFO] 啟動燒錄器於 port: 9000"

python3 server/plasma_server_async.py --port 9001 --ic cc2340r5 > log/server_9001.log 2>&1 &
echo "[INFO] 啟動燒錄器於 port: 9001"

sleep 1

echo "[INFO] 目前監聽中的 port："
netstat -tuln | grep 900

echo "[INFO] 所有燒錄器已啟動完成，按 Ctrl+C 可中止。"
wait

