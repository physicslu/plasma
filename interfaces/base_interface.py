class CommInterface:
    def connect(self):
        raise NotImplementedError

    def send(self, data: bytes):
        raise NotImplementedError

    def receive(self) -> bytes:
        raise NotImplementedError

    def close(self):
        raise NotImplementedError
