import socket
from interfaces.base_interface import CommInterface

class TCPInterface(CommInterface):
    def __init__(self, host='127.0.0.1', port=9000):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port))

    def send(self, data: bytes):
        self.sock.sendall(data)

    def receive(self) -> bytes:
        return self.sock.recv(4096)

    def close(self):
        if self.sock:
            self.sock.close()
