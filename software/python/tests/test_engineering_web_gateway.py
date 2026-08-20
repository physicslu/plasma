from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class FakeEngineeringProvider:
    last_status = None
    last_start = None
    last_cancel = None

    def catalog(self):
        return {
            "ok": True,
            "provider": "mock",
            "facility_count": 3,
            "ppu_count": 12,
            "site_count": 60,
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

    async def start_job(self, facility_id, ppu_id, request):
        FakeEngineeringProvider.last_start = (facility_id, ppu_id, request)
        return {
            "ok": True,
            "job": {
                "job_id": "engineering-job-1",
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "queued",
            },
        }

    async def cancel_job(self, facility_id, ppu_id, job_id):
        FakeEngineeringProvider.last_cancel = (facility_id, ppu_id, job_id)
        return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}

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

    def request(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw else {}
        conn.request(method, path, raw, headers)
        response = conn.getresponse()
        content_type = response.getheader("Content-Type", "")
        data = response.read()
        conn.close()
        payload = json.loads(data) if data and content_type.startswith("application/json") else data
        return response.status, payload

    def test_catalog_comes_from_server_side_provider(self):
        status, payload = self.request("GET", "/api/engineering/targets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["facility_count"], 3)
        self.assertEqual(payload["ppu_count"], 12)
        self.assertEqual(payload["site_count"], 60)

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

    def test_epvr_job_submission_preserves_selected_ppu_identity(self):
        status, payload = self.request(
            "POST",
            "/api/engineering/targets/mock-facility-03/mock-facility-03-ppu-04/api/jobs",
            {"site_id": 8, "operation": "erase"},
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["site_id"], 8)
        facility_id, ppu_id, request = FakeEngineeringProvider.last_start
        self.assertEqual(facility_id, "mock-facility-03")
        self.assertEqual(ppu_id, "mock-facility-03-ppu-04")
        self.assertEqual(request.site_id, 8)
        self.assertEqual(request.client_id, "plasma-web-engineering")

    def test_cancel_and_read_download_route_to_selected_ppu(self):
        status, payload = self.request(
            "POST",
            "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/jobs/engineering-job-1/cancel",
            {},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["job"]["cancel_requested"])
        self.assertEqual(
            FakeEngineeringProvider.last_cancel,
            ("mock-facility-01", "mock-facility-01-ppu-01", "engineering-job-1"),
        )

        status, payload = self.request(
            "GET",
            "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/jobs/engineering-job-1/files/read.bin",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"mock-read-data")


if __name__ == "__main__":
    unittest.main()
