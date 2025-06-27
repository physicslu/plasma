import json
import logging
from server.utils.map_parser import split_binary_by_map

# 模擬的 handler map，可在其他地方擴充
handler_map = {
    "default": lambda data, meta, addr: dummy_handler(data, meta, addr),
    "bootloader": lambda data, meta, addr: dummy_handler(data, meta, addr),
}

async def dummy_handler(data, meta, addr):
    logging.info(f"[{addr}] [dummy_handler] Data size: {len(data)}, meta: {meta}")
    return {"message": "dummy handler executed"}

async def handle_command(command, reader, writer, addr):
    try:
        if command != "/program":
            logging.warning(f"[{addr}] Unknown command: {command}")
            writer.write((json.dumps({"status": "error", "msg": "Unknown command"}) + '\n').encode())
            await writer.drain()
            return

        logging.info(f"[{addr}] Receiving map.json ...")
        map_header = await reader.readline()
        map_size = int(map_header.decode().strip())

        map_data_raw = await reader.readexactly(map_size)
        try:
            map_data = json.loads(map_data_raw.decode())
        except Exception as e:
            logging.error(f"[{addr}] Invalid map.json: {e}")
            writer.write((json.dumps({"status": "error", "msg": f"Invalid map.json: {e}"}) + '\n').encode())
            await writer.drain()
            return

        logging.info(f"[{addr}] Receiving binary data ...")
        bin_header = await reader.readline()
        bin_size = int(bin_header.decode().strip())

        binary_data = await reader.readexactly(bin_size)

        results = []
        sections = split_binary_by_map(binary_data, map_data)

        for idx, section in enumerate(sections):
            handler_name = section["handler"]
            meta = section["meta"]
            data = section["data"]

            try:
                func = handler_map.get(handler_name)
                if not func:
                    raise ValueError(f"Handler '{handler_name}' not found")

                logging.info(f"[{addr}] Section {idx} -> handler: {handler_name}")
                result = await func(data, meta, addr)

                results.append({
                    "index": idx,
                    "handler": handler_name,
                    "status": "ok",
                    "meta": meta,
                    **result
                })

            except Exception as e:
                logging.error(f"[{addr}] Section {idx} failed: {e}")
                results.append({
                    "index": idx,
                    "handler": handler_name,
                    "status": "error",
                    "msg": str(e),
                    "meta": meta
                })

        response = {
            "status": "done",
            "results": results
        }

        writer.write((json.dumps(response) + '\n').encode())
        await writer.drain()

    except Exception as e:
        logging.exception(f"[{addr}] Unexpected error: {e}")
        writer.write((json.dumps({
            "status": "error",
            "msg": f"Internal error: {str(e)}"
        }) + '\n').encode())
        await writer.drain()

