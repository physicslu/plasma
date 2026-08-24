from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
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

    def test_engineering_job_target_device_resolves_to_canonical_job_target(self) -> None:
        record = get_default_device_catalog().search("ADUC7019BCPZ62I", limit=1)[0]
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)

        request = handler._job_request(
            {
                "site_id": 1,
                "operation": "erase",
                "target_device": {
                    "vendor": record.vendor,
                    "identifier": record.identifier,
                },
            },
            client_id="plasma-web-engineering",
            allow_inline_asset=False,
        )

        self.assertEqual(request.target, record.icpn or record.identifier)
        self.assertEqual(request.metadata["target_device"]["vendor"], record.vendor)
        self.assertEqual(request.metadata["target_device"]["identifier"], record.identifier)
        self.assertEqual(request.metadata["target_device"]["identifier_kind"], record.identifier_kind)

    def test_engineering_job_target_device_fails_closed_when_not_canonical(self) -> None:
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)

        with self.assertRaisesRegex(ValueError, "canonical Device Catalog record"):
            handler._job_request(
                {
                    "site_id": 1,
                    "operation": "erase",
                    "target_device": {
                        "vendor": "UNKNOWN-VENDOR",
                        "identifier": "NOT-A-REAL-DEVICE",
                    },
                },
                client_id="plasma-web-engineering",
                allow_inline_asset=False,
            )


if __name__ == "__main__":
    unittest.main()
