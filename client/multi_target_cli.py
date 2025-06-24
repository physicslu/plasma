import argparse
import asyncio
import json
import os
import socket
import time
import random
from datetime import datetime
from collections import defaultdict
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TaskProgressColumn, TransferSpeedColumn

CHUNK_SIZE = 1024
LOG_PATH = "log/cli_multi.log"

summary_results = defaultdict(list)

def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_PATH, "a") as f:
        f.write(f"{timestamp} {msg}\n")


async def send_channel(ip, port, ch, firmware_data, slow, progress, task_id):
    label = f"{ip}:{port} CH{ch}"
    try:
        reader, writer = await asyncio.open_connection(ip, port)
        writer.write(f"CH{ch}:".encode())
        await writer.drain()

        total_size = len(firmware_data)
        sent = 0
        for i in range(0, total_size, CHUNK_SIZE):
            chunk = firmware_data[i:i + CHUNK_SIZE]
            writer.write(chunk)
            await writer.drain()
            sent += len(chunk)
            progress.update(task_id, completed=sent)
            if slow:
                await asyncio.sleep(0.05 + random.uniform(0, 0.05))

        writer.close()
        await writer.wait_closed()
        progress.console.print(f"[✔ {label}] 傳送完成 {total_size} bytes")
        summary_results[f"{ip}:{port}"].append((ch, "✔", total_size))
        log(f"Sent to {label} → {total_size} bytes")

    except Exception as e:
        progress.stop_task(task_id)
        progress.console.print(f"[✘ {label}] Error: {e}")
        summary_results[f"{ip}:{port}"].append((ch, "✘", str(e)))
        log(f"Error with {label}: {e}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True, help="Path to targets.json")
    parser.add_argument("--file", required=True, help="Firmware binary file")
    parser.add_argument("--debug", action="store_true", help="Enable verbose output")
    parser.add_argument("--slow", action="store_true", help="Slow mode (add delay per chunk)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ Firmware file not found: {args.file}")
        return

    with open(args.file, "rb") as f:
        firmware_data = f.read()

    with open(args.targets, "r") as f:
        targets = json.load(f)

    tasks = []
    progress = Progress(
        "[bold blue]{task.description}",
        BarColumn(),
        TaskProgressColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        transient=False  # 保留畫面
    )

    with progress:
        for t in targets:
            ip = t.get("ip")
            port = t.get("port", 9000)
            channels = t.get("channels", [0])
            for ch in channels:
                task_id = progress.add_task(f"{ip}:{port} CH{ch}", total=len(firmware_data))
                tasks.append(send_channel(ip, port, ch, firmware_data, args.slow, progress, task_id))

        await asyncio.gather(*tasks)

    print("\n=== Summary by Device ===")
    for device in sorted(summary_results):
        print(f"[{device}]")
        for ch, status, info in sorted(summary_results[device]):
            print(f"  {status} CH{ch} - {info}")


def entrypoint():
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()

