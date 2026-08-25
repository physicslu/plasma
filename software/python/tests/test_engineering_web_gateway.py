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
    last_begin_session = None
    last_cache_check = None
    last_cache_upload = None

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

    def begin_session(self, previous_session_id=None):
        FakeEngineeringProvider.last_begin_session = previous_session_id
        return {
            "ok": True,
            "session": {
                "session_id": "1" * 32,
                "programming_asset_cache_scope": "connection-session-and-ppu",
                "previous_session_cleared": previous_session_id is not None,
            },
        }

    def asset_cache_status(
        self,
        session_id,
        facility_id,
        ppu_id,
        asset_name,
        asset_type,
        asset_format,
        asset_size,
        asset_sha256,
    ):
        FakeEngineeringProvider.last_cache_check = (
            session_id,
            facility_id,
            ppu_id,
            asset_name,
            asset_type,
            asset_format,
            asset_size,
            asset_sha256,
        )
        return {
            "ok": True,
            "programming_asset": {
                "cache_hit": False,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "asset_format": asset_format,
                "asset_size": asset_size,
                "asset_sha256": asset_sha256,
            },
        }

    def cache_asset(
        self,
        session_id,
        facility_id,
        ppu_id,
        asset_name,
        asset_type,
        asset_format,
        asset_sha256,
        data,
    ):
        FakeEngineeringProvider.last_cache_upload = (
            session_id,
            facility_id,
            ppu_id,
            asset_name,
            asset_type,
            asset_format,
            asset_sha256,
            data,
        )
        return {
            "ok": True,
            "programming_asset": {
                "cache_hit": True,
                "uploaded": True,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "asset_format": asset_format,
                "asset_size": len(data),
                "asset_sha256": asset_sha256,
            },
        }

    def job_timeout_s(self, facility_id, ppu_id):
        return 90.0

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

    async def start_job(
        self,
        facility_id,
        ppu_id,
        request,
        *,
        session_id=None,
        asset_sha256=None,
    ):
        FakeEngineeringProvider.last_start = (
            facility_id,
            ppu_id,
            request,
            session_id,
            asset_sha256,
        )
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

    def test_reconnect_starts_new_session_and_passes_previous_session_for_clear(self):
        previous = "a" * 32
        status, payload = self.request(
            "POST",
            "/api/engineering/session",
            {"previous_session_id": previous},
        )
        self.assertEqual(status, 201)
        self.assertEqual(FakeEngineeringProvider.last_begin_session, previous)
        self.assertTrue(payload["session"]["previous_session_cleared"])
        self.assertEqual(payload["session"]["session_id"], "1" * 32)
        self.assertEqual(
            payload["session"]["programming_asset_cache_scope"],
            "connection-session-and-ppu",
        )

    def test_asset_probe_and_upload_route_to_selected_ppu(self):
        session_id = "1" * 32
        sha256 = "b" * 64
        base = "/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03"
        status, payload = self.request(
            "POST",
            f"{base}/api/programming-assets/check",
            {
                "session_id": session_id,
                "asset_name": "one.bin",
                "asset_type": "image",
                "asset_format": "binary",
                "asset_size": 1024,
                "asset_sha256": sha256,
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["programming_asset"]["cache_hit"])
        self.assertEqual(
            FakeEngineeringProvider.last_cache_check,
            (session_id, "mock-facility-02", "mock-facility-02-ppu-03", "one.bin", "image", "binary", 1024, sha256),
        )

        data = b"image-bytes"
        status, payload = self.request(
            "POST",
            f"{base}/api/programming-assets?session_id={session_id}&name=one.bin&type=image&format=binary&sha256={sha256}",
            raw_body=data,
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 201)
        self.assertTrue(payload["programming_asset"]["uploaded"])
        self.assertEqual(
            FakeEngineeringProvider.last_cache_upload,
            (session_id, "mock-facility-02", "mock-facility-02-ppu-03", "one.bin", "image", "binary", sha256, data),
        )

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
        facility_id, ppu_id, request, session_id, asset_sha256 = FakeEngineeringProvider.last_start
        self.assertEqual(facility_id, "mock-facility-03")
        self.assertEqual(ppu_id, "mock-facility-03-ppu-04")
        self.assertEqual(request.site_id, 8)
        self.assertEqual(request.client_id, "plasma-web-engineering")
        self.assertEqual(request.timeout_s, 90.0)
        self.assertIsNone(session_id)
        self.assertIsNone(asset_sha256)

    def test_program_submission_sends_only_session_asset_reference(self):
        session_id = "2" * 32
        sha256 = "c" * 64
        status, payload = self.request(
            "POST",
            "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-02/api/jobs",
            {
                "site_id": 2,
                "operation": "program",
                "session_id": session_id,
                "asset_sha256": sha256,
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["operation"], "program")
        facility_id, ppu_id, request, routed_session, routed_sha = FakeEngineeringProvider.last_start
        self.assertEqual((facility_id, ppu_id), ("mock-facility-01", "mock-facility-01-ppu-02"))
        self.assertEqual(request.image, b"")
        self.assertEqual(request.timeout_s, 90.0)
        self.assertEqual(routed_session, session_id)
        self.assertEqual(routed_sha, sha256)

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
