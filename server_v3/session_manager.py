import logging
from handlers.ic_cc2340r5_handler import handle_command

async def handle_session(reader, writer):
    addr = writer.get_extra_info('peername')
    logging.info(f"[+] Connected: {addr}")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            command = line.decode().strip()
            logging.info(f"[{addr}] Command: {command}")

            if command in ["/erase", "/program", "/verify", "/read"]:
                await handle_command(command, reader, writer, addr)
            else:
                msg = f'{{"status": "error", "msg": "Unknown command: {command}"}}\n'
                writer.write(msg.encode())
                await writer.drain()
    except Exception as e:
        logging.error(f"[!] Error from {addr}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        logging.info(f"[-] Disconnected: {addr}")

