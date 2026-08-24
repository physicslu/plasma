from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class DeviceCatalogWebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path: str):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_exact_icpn_search_exposes_catalog_without_ppu_runtime(self) -> None:
        status, payload = self.request("/api/devices/search?q=ADUC7019BCPZ62I&limit=5")

        self.assertEqual(status, 200)
        self.assertEqual(payload["rest_contract_version"], "3")
        self.assertEqual(payload["catalog_size"], 7657)
        self.assertEqual(payload["results"][0]["icpn"], "ADUC7019BCPZ62I")
        self.assertEqual(payload["results"][0]["identifier_kind"], "manufacturer_part_number")
        self.assertEqual(payload["results"][0]["physical_validation"]["ppu_status"], "no_evidence")
        self.assertEqual(payload["results"][0]["physical_validation"]["socket_status"], "no_evidence")

    def test_search_is_case_insensitive(self) -> None:
        status, payload = self.request("/api/devices/search?q=aduc7019bcpz62i")

        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["identifier"], "ADUC7019BCPZ62I")

    def test_empty_query_is_valid_for_autocomplete_idle_state(self) -> None:
        status, payload = self.request("/api/devices/search?q=")

        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_invalid_limit_fails_closed(self) -> None:
        status, payload = self.request("/api/devices/search?q=ADUC&limit=101")

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["error_type"], "INVALID_DEVICE_SEARCH")


if __name__ == "__main__":
    unittest.main()
