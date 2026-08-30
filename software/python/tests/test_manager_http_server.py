from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from plasma_manager.server import PlasmaManagerHandler, PlasmaManagerHTTPServer


class PlasmaManagerHTTPServerTests(unittest.TestCase):
    def test_bind_does_not_resolve_fqdn(self) -> None:
        with patch.object(
            socket,
            "getfqdn",
            side_effect=AssertionError("Manager bind must not depend on DNS"),
        ):
            server = PlasmaManagerHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        try:
            self.assertEqual(server.server_name, "127.0.0.1")
            self.assertGreater(server.server_port, 0)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
