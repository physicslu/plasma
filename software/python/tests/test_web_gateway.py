from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_web.gateway import PlasmaWebHandler


class FakeClient:
    last_request = None
    last_status_kwargs = None

    async def status(self, **kwargs):
        FakeClient.last_status_kwargs = kwargs
        return {
            "ok": True,
            "ppu": {"ppu_id": "ppu-test", "facility_id": "facility-test"},
            "sites": [{"site_id": 1}],
        }

    async def start(self, request):
        FakeClient.last_request = request
        return {"ok": True, "job": {"job_id": "web-job-1", "site_id": request.site_id, "state": "queued"}}

    async def cancel(self, job_id):
        return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}


class WebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output_root = Path(cls.temporary.name)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.addClassCleanup(setattr, PlasmaWebHandler, "output_root", PlasmaWebHandler.output_root)
        cls.addClassCleanup(setattr, PlasmaWebHandler, "client_factory", PlasmaWebHandler.client_factory)
        PlasmaWebHandler.client_factory = staticmethod(FakeClient)
        PlasmaWebHandler.output_root = cls.output_root
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        request_headers = dict(headers or {})
        if raw:
            request_headers["Content-Type"] = "application/json"
        conn.request(method, path, raw, request_headers)
        response = conn.getresponse()
        response_headers = dict(response.getheaders())
        response_body = response.read()
        conn.close()
        payload = (
            json.loads(response_body)
            if response_body and response_headers.get("Content-Type", "").startswith("application/json")
            else (response_body or None)
        )
        return response.status, payload, response_headers

    def test_status(self):
        status, payload, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("ppu", payload)
        self.assertIn("sites", payload)

    def test_status_accepts_canonical_site_query(self):
        status, payload, _ = self.request("GET", "/api/status?site=1")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(FakeClient.last_status_kwargs["site_id"], 1)

    def test_status_retains_legacy_channel_zero_query(self):
        status, payload, _ = self.request("GET", "/api/status?channel=0")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(FakeClient.last_status_kwargs["site_id"], 1)

    def test_status_rejects_conflicting_site_and_channel(self):
        status, payload, _ = self.request("GET", "/api/status?site=1&channel=1")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_start_program_upload_uses_one_based_site_id(self):
        firmware = b"\x01\x02\x03"
        status, payload, _ = self.request(
            "POST",
            "/api/jobs",
            {
                "site_id": 1,
                "operation": "program",
                "firmware_name": "fw.bin",
                "firmware_base64": base64.b64encode(firmware).decode(),
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["job_id"], "web-job-1")
        self.assertEqual(FakeClient.last_request.firmware, firmware)
        self.assertEqual(FakeClient.last_request.site_id, 1)
        self.assertEqual(FakeClient.last_request.channel_id, 0)

    def test_start_job_translates_legacy_channel_zero_to_site_one(self):
        status, payload, _ = self.request(
            "POST", "/api/jobs", {"channel_id": 0, "operation": "erase"}
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["job_id"], "web-job-1")
        self.assertEqual(FakeClient.last_request.site_id, 1)

    def test_start_job_accepts_matching_site_and_legacy_channel(self):
        status, payload, _ = self.request(
            "POST", "/api/jobs", {"site_id": 1, "channel_id": 0, "operation": "erase"}
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["site_id"], 1)

    def test_start_job_rejects_conflicting_site_and_channel(self):
        status, payload, _ = self.request(
            "POST", "/api/jobs", {"site_id": 1, "channel_id": 1, "operation": "erase"}
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_start_job_rejects_non_integer_or_zero_site_id(self):
        for site_id in (True, 1.5, 0, -1, "1.5"):
            with self.subTest(site_id=site_id):
                status, payload, _ = self.request(
                    "POST", "/api/jobs", {"site_id": site_id, "operation": "erase"}
                )
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])

    def test_verify_requires_firmware(self):
        status, payload, _ = self.request(
            "POST", "/api/jobs", {"site_id": 1, "operation": "verify"}
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_read_without_firmware_uses_logical_range(self):
        status, _, _ = self.request(
            "POST", "/api/jobs", {"site_id": 1, "operation": "read", "offset": 12, "length": 4}
        )
        self.assertEqual(status, 202)
        self.assertEqual(FakeClient.last_request.firmware, b"")
        self.assertEqual(
            FakeClient.last_request.map_data["sections"],
            [{"name": "flash", "address": 12, "length": 4}],
        )

    def test_read_rejects_invalid_range(self):
        status, payload, _ = self.request(
            "POST", "/api/jobs", {"site_id": 1, "operation": "read", "offset": -1, "length": 4}
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_read_rejects_non_integer_and_non_positive_ranges(self):
        invalid_ranges = [
            {"offset": True, "length": 4},
            {"offset": 1.5, "length": 4},
            {"offset": "1", "length": 4},
            {"offset": 0, "length": False},
            {"offset": 0, "length": 1.5},
            {"offset": 0, "length": "4"},
            {"offset": 0, "length": 0},
            {"offset": 0, "length": -1},
        ]
        for values in invalid_ranges:
            with self.subTest(**values):
                status, payload, _ = self.request(
                    "POST", "/api/jobs", {"site_id": 1, "operation": "read", **values}
                )
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])

    def test_download_is_job_scoped_and_binary(self):
        job_dir = self.output_root / "web-job-1"
        job_dir.mkdir(exist_ok=True)
        output = job_dir / "read_SITE1_flash.bin"
        output.write_bytes(b"\x01\x02\xff")
        (job_dir / "result.json").write_text(json.dumps({"output_files": [str(output)]}))
        status, payload, headers = self.request(
            "GET", "/api/jobs/web-job-1/files/read_SITE1_flash.bin"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"\x01\x02\xff")
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertIn("read_SITE1_flash.bin", headers["Content-Disposition"])

        other = self.output_root / "other-job"
        other.mkdir(exist_ok=True)
        secret = other / "secret.bin"
        secret.write_bytes(b"secret")
        status, payload, _ = self.request("GET", "/api/jobs/web-job-1/files/secret.bin")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_download_rejects_path_traversal(self):
        status, payload, _ = self.request(
            "GET", "/api/jobs/web-job-1/files/%2e%2e%2fresult.json"
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_cancel(self):
        status, payload, _ = self.request("POST", "/api/jobs/web-job-1/cancel", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["job"]["cancel_requested"])

    def test_cors_preflight(self):
        status, payload, headers = self.request(
            "OPTIONS",
            "/api/jobs",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(status, 204)
        self.assertIsNone(payload)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])


if __name__ == "__main__":
    unittest.main()
