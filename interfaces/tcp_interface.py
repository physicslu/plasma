import socket

class TCPInterface:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        print(f"🔗 Connecting to {self.host}:{self.port}")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

    def send(self, data: bytes):
        if not self.sock:
            raise RuntimeError("Socket not connected")
        self.sock.sendall(data)

    def recv_until(self, delimiter: bytes = b'\n') -> bytes:
        if not self.sock:
            raise RuntimeError("Socket not connected")
        buf = b""
        while True:
            chunk = self.sock.recv(1024)
            if not chunk:
                break
            buf += chunk
            if delimiter in buf:
                break
        return buf

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

