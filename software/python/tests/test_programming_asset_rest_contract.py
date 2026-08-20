from __future__ import annotations

import base64
import hashlib
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler, WEB_REST_CONTRACT_VERSION


class FakeProgrammingAssetProvider:
    last_begin_session = None
    last_cache_check = None
    last_cache_upload = None
    last_start = None

    def catalog(self):
        return {
            "ok": True,
            "provider": "mock",
            "facility_count": 1,
            "ppu_count": 1,
            "site_count": 2,
            "programming_asset_scope": "connection-session-and-ppu",
            "supported_asset_types": ["image", "key", "option", "serial_number", "calibration"],
            "supported_asset_formats": ["binary", "intel_hex", "csv", "text"],
            "implemented_normalizers": [
                {"asset_type": "image", "asset_format": "binary", "output": "normalized_image"}
            ],
            "facilities": [],
        }

    def begin_session(self, previous_session_id=None):
        self.last_begin_session = previous_session_id
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
        self.last_cache_check = (
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
        self.last_cache_upload = (
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
        return {
            "ok": True,
            "ppu": {
                "ppu_id": ppu_id,
                "facility_id": facility_id,
                "model": "MOCK-PPU",
                "display_name": ppu_id,
                "site_count": 2,
                "enabled_site_count": 2,
                "capabilities": {
                    "max_supported_sites": 2,
                    "operations": ["erase", "program", "verify", "read"],
                },
            },
            "sites": [],
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
        self.last_start = (facility_id, ppu_id, request, session_id, asset_sha256)
        return {
            "ok": True,
            "job": {
                "job_id": "programming-asset-job-1",
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "queued",
            },
        }

    async def cancel_job(self, facility_id, ppu_id, job_id):
        return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}

    def read_output_file(self, facility_id, ppu_id, job_id, filename):
        return b""


class ProgrammingAssetRestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_provider = PlasmaWebHandler.engineering_provider
        cls.provider = FakeProgrammingAssetProvider()
        PlasmaWebHandler.engineering_provider = cls.provider
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.target = "/api/engineering/targets/facility-01/ppu-01"

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

    def test_catalog_and_session_publish_rest_v3_asset_contract(self):
        status, payload = self.request("GET", "/api/engineering/targets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rest_contract_version"], WEB_REST_CONTRACT_VERSION)
        self.assertEqual(WEB_REST_CONTRACT_VERSION, "3")
        self.assertEqual(payload["programming_asset_scope"], "connection-session-and-ppu")
        self.assertIn("serial_number", payload["supported_asset_types"])

        status, payload = self.request("POST", "/api/engineering/session", {})
        self.assertEqual(status, 201)
        self.assertEqual(payload["rest_contract_version"], "3")
        self.assertEqual(
            payload["session"]["programming_asset_cache_scope"],
            "connection-session-and-ppu",
        )

    def test_programming_asset_check_and_upload_routes(self):
        session_id = "1" * 32
        data = b"image-bytes"
        sha256 = hashlib.sha256(data).hexdigest()
        status, payload = self.request(
            "POST",
            f"{self.target}/api/programming-assets/check",
            {
                "session_id": session_id,
                "asset_name": "image.bin",
                "asset_type": "image",
                "asset_format": "binary",
                "asset_size": len(data),
                "asset_sha256": sha256,
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["programming_asset"]["cache_hit"])
        self.assertEqual(payload["programming_asset"]["asset_name"], "image.bin")
        self.assertEqual(
            self.provider.last_cache_check,
            (session_id, "facility-01", "ppu-01", "image.bin", "image", "binary", len(data), sha256),
        )

        status, payload = self.request(
            "POST",
            f"{self.target}/api/programming-assets?session_id={session_id}&name=image.bin&type=image&format=binary&sha256={sha256}",
            raw_body=data,
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 201)
        self.assertTrue(payload["programming_asset"]["uploaded"])
        self.assertEqual(
            self.provider.last_cache_upload,
            (session_id, "facility-01", "ppu-01", "image.bin", "image", "binary", sha256, data),
        )

    def test_engineering_job_references_cached_asset_only(self):
        session_id = "2" * 32
        sha256 = "b" * 64
        status, payload = self.request(
            "POST",
            f"{self.target}/api/jobs",
            {
                "site_id": 2,
                "operation": "program",
                "session_id": session_id,
                "asset_sha256": sha256,
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["operation"], "program")
        _, _, request, routed_session, routed_sha = self.provider.last_start
        self.assertEqual(request.image, b"")
        self.assertEqual(routed_session, session_id)
        self.assertEqual(routed_sha, sha256)

    def test_local_job_materializes_asset_then_normalizes_image(self):
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        data = b"inline-image"
        encoded = base64.b64encode(data).decode()
        sha256 = hashlib.sha256(data).hexdigest()
        request = handler._job_request(
            {
                "site_id": 1,
                "operation": "program",
                "asset_name": "inline.bin",
                "asset_type": "image",
                "asset_format": "binary",
                "asset_sha256": sha256,
                "asset_base64": encoded,
            },
            client_id="test-client",
        )
        self.assertEqual(request.image, data)
        self.assertEqual(request.metadata["image_name"], "inline.bin")
        self.assertEqual(request.metadata["source_asset_sha256"], sha256)

    def test_non_image_asset_cannot_be_used_as_inline_program_image(self):
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        data = b"SN-000003"
        encoded = base64.b64encode(data).decode()
        sha256 = hashlib.sha256(data).hexdigest()
        with self.assertRaises(Exception):
            handler._job_request(
                {
                    "site_id": 1,
                    "operation": "program",
                    "asset_name": "serial.txt",
                    "asset_type": "serial_number",
                    "asset_format": "text",
                    "asset_sha256": sha256,
                    "asset_base64": encoded,
                },
                client_id="test-client",
            )

    def test_retired_rest_routes_are_not_available(self):
        for path in (
            f"{self.target}/api/programming-images/check",
            f"{self.target}/api/firmware/check",
        ):
            with self.subTest(path=path):
                status, _payload = self.request("POST", path, {})
                self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
