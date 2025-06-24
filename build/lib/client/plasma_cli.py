import argparse
import os
import time
from datetime import datetime
from interfaces.tcp_interface import TCPInterface
from interfaces.usb_winusb_interface import WinUSBInterface

LOG_PATH = "log/cli.log"
CHUNK_SIZE = 1024

def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_PATH, "a") as f:
        f.write(f"{timestamp} {msg}\n")

def get_interface(name):
    if name == "tcp":
        return TCPInterface()
    elif name == "usb":
        return WinUSBInterface()
    else:
        raise ValueError("Unsupported interface: " + name)

def send_with_progress(iface, data, total_size, debug=False, target_host="127.0.0.1", target_port=9000):
    sent = 0
    bar_width = 30

    print(f"🔗 Connecting to {target_host}:{target_port}")
    print("🚀 Starting transmission...\n")

    for i in range(0, total_size, CHUNK_SIZE):
        chunk = data[i:i+CHUNK_SIZE]
        iface.send(chunk)
        sent += len(chunk)
        percent = sent / total_size
        filled = int(bar_width * percent)
        bar = "#" * filled + " " * (bar_width - filled)
        print(f"\rSending... [{bar}] {int(percent * 100)}% ({sent} / {total_size} bytes)", end="", flush=True)
        if debug:
            time.sleep(0.05)
    print("\n✅ Sending complete.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Input binary file')
    parser.add_argument('--interface', default='tcp', choices=['tcp', 'usb'], help='Communication interface')
    parser.add_argument('--host', default='127.0.0.1', help='Target IP address')
    parser.add_argument('--port', type=int, default=9000, help='Target TCP port')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with slow progress display')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        return

    with open(args.file, 'rb') as f:
        data = f.read()

    iface = get_interface(args.interface)
    iface.connect()

    total_size = len(data)
    log(f"Start sending: {args.file} ({total_size} bytes) to {args.host}:{args.port} via {args.interface}")
    send_with_progress(iface, data, total_size, debug=args.debug, target_host=args.host, target_port=args.port)
    log(f"Sent {total_size} bytes → OK")

    iface.close()

if __name__ == '__main__':
    main()

