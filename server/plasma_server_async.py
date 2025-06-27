import asyncio
import argparse
import logging

# 初始化 Logger
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# 模擬燒錄邏輯（簡化範例）
async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    logging.info(f"Connected with {addr}")
    try:
        data = await reader.read(4096)
        logging.info(f"Received {len(data)} bytes from {addr}")
        await asyncio.sleep(1)  # 模擬處理
    except Exception as e:
        logging.error(f"Error with {addr}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, host='0.0.0.0', port=args.port)
    logging.info(f"Server running on port {args.port} for IC: {args.ic}")
    async with server:
        await server.serve_forever()

# 解析命令列參數
parser = argparse.ArgumentParser(description="Plasma async server")
parser.add_argument('--port', type=int, default=9000, help='Port to listen on')
parser.add_argument('--ic', type=str, default='cc2340r5', help='IC model for handler')
args = parser.parse_args()

# 啟動主程式
if __name__ == '__main__':
    asyncio.run(main())

