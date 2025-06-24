# 目前仍以 TCP 為主，不抽換 interface。未來如使用 USB 接收端點則在此擴充。

import asyncio

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"Connected with {addr}")

    while True:
        data = await reader.read(4096)
        if not data:
            break
        print(f"Received {len(data)} bytes.")
        # 模擬燒錄處理
        await asyncio.sleep(0.1)

    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', 9000)
    async with server:
        print("Server running on port 9000...")
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
