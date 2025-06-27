import asyncio
import logging

async def default_handler(data, meta, addr):
    logging.info(f"[{addr}] [default] Write {len(data)} bytes to {meta['target']}")
    await asyncio.sleep(0.1)
    return {"status": "ok"}

async def otp_handler(data, meta, addr):
    logging.info(f"[{addr}] [otp] Program OTP {len(data)} bytes at {meta['target']}")
    await asyncio.sleep(0.2)
    return {"status": "ok"}

async def handle_bootloader(section, writer):
    addr = section['target']
    data = section['data']
    await asyncio.sleep(0.3)  # 模擬 Bootloader 特殊加密處理
    print(f"[bootloader] Encrypted write of {len(data)} bytes to {addr}")
    return f"[bootloader] wrote {len(data)} bytes to {addr}"

# handler map 可供外部呼叫
handler_map = {
    "default": default_handler,
    "otp": otp_handler,
    "bootloader": handle_bootloader,
}

