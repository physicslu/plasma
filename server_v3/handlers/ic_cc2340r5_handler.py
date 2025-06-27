import asyncio
import json
import logging

async def handle_command(command, reader, writer, addr):
    if command in ["/program", "/verify"]:
        data = b''
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            data += chunk

        size = len(data)
        logging.info(f"[{addr}] Received {size} bytes for {command}")

        # 模擬處理
        await asyncio.sleep(1)

        response = {"status": "ok", "command": command, "size": size}
        writer.write((json.dumps(response) + '\n').encode())
        await writer.drain()

    elif command == "/erase":
        logging.info(f"[{addr}] Erasing memory (mock)")
        await asyncio.sleep(0.5)
        writer.write(b'{"status": "ok", "command": "erase"}\n')
        await writer.drain()

    elif command == "/read":
        dummy_data = b'\xDE\xAD\xBE\xEF' * 64  # 256 bytes
        logging.info(f"[{addr}] Sending dummy read data ({len(dummy_data)} bytes)")
        writer.write(dummy_data)
        await writer.drain()

