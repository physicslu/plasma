import asyncio
import struct
import logging
import json

from server.handlers import load_handler_map
from server.session_manager import handle_session

HOST = '0.0.0.0'
PORT = 9000
handler_dir = "server/handlers"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("PlasmaServer")


async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    logger.info(f"[+] Connected: {addr}")

    try:
        # Step 1: Read command
        command_line = await reader.readline()
        command = command_line.decode(errors='ignore').strip()
        logger.info(f"[{addr}] Command: {command}")

        if command == "/program":
            # Step 2: Read MAPSIZE (4 bytes)
            header = await reader.readexactly(4)
            (mapsize,) = struct.unpack("<I", header)

            logger.info(f"[{addr}] Receiving map.json ({mapsize} bytes)...")
            map_data_raw = await reader.readexactly(mapsize)

            try:
                map_data = json.loads(map_data_raw.decode())
            except Exception as e:
                logger.error(f"[{addr}] Invalid map.json: {e}")
                writer.write(f"ERROR: Invalid map.json: {e}\n".encode())
                await writer.drain()
                return

            # Step 3: Read BINLEN (4 bytes)
            bin_header = await reader.readexactly(4)
            (binlen,) = struct.unpack("<I", bin_header)

            logger.info(f"[{addr}] Receiving binary data ({binlen} bytes)...")
            binary_data = await reader.readexactly(binlen)

            # Step 4: Handle via session dispatcher
            try:
                handler_map = load_handler_map(handler_dir)
                await handle_session(command, map_data, binary_data, writer, addr, handler_map, handler_dir)
            except Exception as e:
                logger.exception(f"[{addr}] Unexpected error: {e}")
                writer.write(f"ERROR: {e}\n".encode())
                await writer.drain()
                return

        else:
            logger.warning(f"[{addr}] Unknown command: {command}")
            writer.write(b"ERROR: Unknown command\n")
            await writer.drain()

    except (asyncio.IncompleteReadError, ConnectionResetError):
        logger.warning(f"[-] Disconnected: {addr}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"[-] Disconnected: {addr}")


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    logger.info(f"[+] Plasma server listening on port {PORT}")
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())

