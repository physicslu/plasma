import asyncio
import logging
from session_manager import handle_session

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

async def main():
    server = await asyncio.start_server(handle_session, host='0.0.0.0', port=9000)
    logging.info(f"[+] Plasma server listening on port 9000")
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())

