import json
import logging
from server.utils.map_parser import split_binary_by_map

logger = logging.getLogger(__name__)

async def handle_session(command, map_data, binary_data, writer, addr, handler_map, handler_dir):
    try:
        if command != "/program":
            logger.warning(f"[{addr}] Unknown command: {command}")
            writer.write(b"ERROR: Unknown command\n")
            await writer.drain()
            return

        logger.info(f"[{addr}] Dispatching to handler...")

        sections = split_binary_by_map(binary_data, map_data)
        results = []

        for idx, section in enumerate(sections):
            handler_name = section.get("handler")
            meta = section.get("meta", {})
            data = section.get("data", b"")

            try:
                func = handler_map.get(handler_name)
                if not func:
                    raise ValueError(f"Handler '{handler_name}' not found")

                logger.info(f"[{addr}] Section {idx} -> handler: {handler_name}")
                result = await func(data, meta, addr)

                results.append({
                    "index": idx,
                    "handler": handler_name,
                    "status": "ok",
                    "meta": meta,
                    **result
                })
            except Exception as e:
                logger.error(f"[{addr}] Section {idx} failed: {e}")
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
        writer.write((json.dumps(response, ensure_ascii=False) + '\n').encode())
        await writer.drain()

    except Exception as e:
        logger.exception(f"[{addr}] Fatal session error: {e}")
        writer.write(f"ERROR: {str(e)}\n".encode())
        await writer.drain()

