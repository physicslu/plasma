# 範例 IC 模組 handler

from server.handlers.section_handlers import default_handler, bootloader_handler

async def preprocess_file(raw_data: bytes, map_data: list):
    # 可根據 map_data 進行切割、解碼、CRC 或加密處理
    return raw_data

handler_map = {
    "default": default_handler,
    "bootloader": bootloader_handler,
}

