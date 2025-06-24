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

def send_with_progress(iface, data, total_size):
    sent = 0
    for i in range(0, total_size, CHUNK_SIZE):
        chunk = data[i:i+CHUNK_SIZE]
        iface.send(chunk)
        sent += len(chunk)
        percent = int((sent / total_size) * 100)
        print(f"\rSending... {sent} / {total_size} bytes ({percent}%)", end="", flush=True)
        time.sleep(0.01)  # 模擬傳送延遲（可移除）
    print("\n✅ Sending complete.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Input binary file')
    parser.add_argument('--interface', default='tcp', choices=['tcp', 'usb'], help='Communication interface')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        return

    with open(args.file, 'rb') as f:
        data = f.read()

    iface = get_interface(args.interface)
    iface.connect()

    total_size = len(data)
    log(f"Start sending: {args.file} ({total_size} bytes) via {args.interface}")
    send_with_progress(iface, data, total_size)
    log(f"Sent {total_size} bytes → OK")

    iface.close()

if __name__ == '__main__':
    main()

