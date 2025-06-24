import asyncio
import argparse

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"Connected with {addr}")
    total_received = 0
    while True:
        data = await reader.read(4096)
        if not data:
            break
        total_received += len(data)
        print(f"Received {len(data)} bytes. Total: {total_received}")
    writer.close()
    await writer.wait_closed()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9000, help='TCP port to listen on')
    args = parser.parse_args()

    server = await asyncio.start_server(handle_client, '0.0.0.0', args.port)
    print(f"Server running on port {args.port}...")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())

