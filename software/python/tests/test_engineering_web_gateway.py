from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class FakeEngineeringProvider:
    last_status = None

    def catalog(self):
        return {
            "ok": True,
            "provider": "mock",
            "facility_count": 8,
            "ppu_count": 32,
            "site_count": 160,
            "programming_asset_scope": "connection-session-and-ppu",
            "supported_asset_types": ["image", "key", "option", "serial_number", "calibration"],
            "supported_asset_formats": ["binary", "intel_hex", "csv", "text"],
            "implemented_normalizers": [
                {"asset_type": "image", "asset_format": "binary", "output": "normalized_image"}
            ],
            "facilities": [],
        }

    async def status(self, facility_id, ppu_id, *, site_id=None, job_id=None):
        FakeEngineeringProvider.last_status = (facility_id, ppu_id, site_id, job_id)
        if job_id:
            return {
                "ok": True,
                "job": {
                    "job_id": job_id,
                    "site_id": site_id or 1,
                    "operation": "erase",
                    "state": "success",
                },
            }
        return {
            "ok": True,
            "ppu": {
                "ppu_id": ppu_id,
                "facility_id": facility_id,
                "model": "MOCK-PPU",
                "display_name": ppu_id,
                "site_count": 6,
                "enabled_site_count": 6,
                "capabilities": {"max_supported_sites": 6, "operations": ["erase", "program", "verify", "read"]},
            },
            "sites": [{"site_id": index, "enabled": True, "state": "idle"} for index in range(1, 7)],
        }

    def read_output_file(self, facility_id, ppu_id, job_id, filename):
        return b"mock-read-data"


class EngineeringWebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_provider = PlasmaWebHandler.engineering_provider
        cls.provider = FakeEngineeringProvider()
        PlasmaWebHandler.engineering_provider = cls.provider
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaWebHandler.engineering_provider = cls.previous_provider

    def request(self, method, path, body=None, *, raw_body=None, content_type="application/json"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Content-Type": content_type} if raw is not None else {}
        conn.request(method, path, raw, headers)
        response = conn.getresponse()
        response_content_type = response.getheader("Content-Type", "")
        data = response.read()
        conn.close()
        payload = json.loads(data) if data and response_content_type.startswith("application/json") else data
        return response.status, payload

    def test_catalog_comes_from_server_side_provider(self):
        status, payload = self.request("GET", "/api/engineering/targets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["facility_count"], 8)
        self.assertEqual(payload["ppu_count"], 32)
        self.assertEqual(payload["site_count"], 160)
        self.assertEqual(payload["programming_asset_scope"], "connection-session-and-ppu")
        self.assertIn("serial_number", payload["supported_asset_types"])

    def test_selected_facility_ppu_and_site_reach_provider(self):
        status, payload = self.request(
            "GET",
            "/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/status?site=6",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["ppu"]["site_count"], 6)
        self.assertEqual(
            FakeEngineeringProvider.last_status,
            ("mock-facility-02", "mock-facility-02-ppu-03", 6, None),
        )


    def test_read_download_routes_to_selected_ppu(self):
        status, payload = self.request(
            "GET",
            "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/jobs/engineering-job-1/files/read.bin",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"mock-read-data")

    def test_engineering_provider_has_no_job_or_asset_write_route(self):
        # U7: Programming runs only as a Manager Batch with an ACTIVE
        # Resource Reservation; the Gateway provider is read-only.
        base = "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01"
        for path in (
            "/api/engineering/session",
            f"{base}/api/jobs",
            f"{base}/api/jobs/engineering-job-1/cancel",
            f"{base}/api/programming-assets/check",
            f"{base}/api/programming-assets?session_id=x&name=a&type=image&format=binary&sha256=b",
        ):
            with self.subTest(path=path):
                status, _ = self.request("POST", path, {"site_id": 1, "operation": "erase"})
                self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
