import argparse
import json
import os
import sys
import time
from tqdm import tqdm

from interfaces.tcp_interface import TCPInterface

def log(msg):
    with open("log/plasma_cli.log", "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def send_with_progress(interface, map_path, bin_path, debug=False, target_host=None, target_port=None):
    with open(map_path, "r") as f:
        map_data = f.read()
    with open(bin_path, "rb") as f:
        bin_data = f.read()

    iface = interface(target_host, target_port)
    iface.connect()

    print("🚀 Starting transmission...")

    # Step 1: Send command
    iface.send(b"/program\n")
    time.sleep(0.1)

    # Step 2: Send 4-byte MAPSIZE
    map_bytes = map_data.encode("utf-8")
    iface.send(len(map_bytes).to_bytes(4, "little"))
    iface.send(map_bytes)
    if debug:
        print("📤 Sent map.json")

    # Step 3: Send 4-byte BINLEN
    iface.send(len(bin_data).to_bytes(4, "little"))

    # Step 4: Send binary data with progress
    chunk_size = 1024
    progress = tqdm(total=len(bin_data), unit="B", unit_scale=True)
    for i in range(0, len(bin_data), chunk_size):
        chunk = bin_data[i:i + chunk_size]
        iface.send(chunk)
        progress.update(len(chunk))
    progress.close()
    print("✅ Firmware transmission complete.\n")

    # Step 5: Receive response
    resp = iface.recv_until(b'\n')
    if debug:
        print("📩 Raw response:", resp)
    try:
        result = json.loads(resp.decode())
        print("📝 Response:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Failed to parse response: {e}")
        print("Raw:", resp)

 # Step 6: Close interface
    iface.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", choices=["tcp"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--map", required=True, help="Path to map.json")
    parser.add_argument("--file", required=True, help="Path to firmware binary")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    iface = None
    if args.interface == "tcp":
        iface = TCPInterface

    if iface:
        send_with_progress(iface, args.map, args.file, debug=args.debug, target_host=args.host, target_port=args.port)
    else:
        print("Unsupported interface")
        sys.exit(1)

if __name__ == "__main__":
    main()

