import argparse
from interfaces.tcp_interface import TCPInterface
from interfaces.usb_winusb_interface import WinUSBInterface

def get_interface(name):
    if name == "tcp":
        return TCPInterface()
    elif name == "usb":
        return WinUSBInterface()
    else:
        raise ValueError("Unsupported interface: " + name)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Input binary file')
    parser.add_argument('--interface', default='tcp', choices=['tcp', 'usb'], help='Communication interface')
    args = parser.parse_args()

    with open(args.file, 'rb') as f:
        data = f.read()

    iface = get_interface(args.interface)
    iface.connect()
    iface.send(data)
    print("Data sent.")
    iface.close()

if __name__ == '__main__':
    main()
