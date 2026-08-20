from __future__ import annotations

import base64
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler, WEB_REST_CONTRACT_VERSION


class FakeProgrammingImageProvider:
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
            "firmware_scope": "connection-session-and-ppu",
            "facilities": [],
        }

    def begin_session(self, previous_session_id=None):
        self.last_begin_session = previous_session_id
        return {
            "ok": True,
            "session": {
                "session_id": "1" * 32,
                "firmware_cache_scope": "connection-session-and-ppu",
                "previous_session_cleared": previous_session_id is not None,
            },
        }

    def firmware_cache_status(
        self,
        session_id,
        facility_id,
        ppu_id,
        firmware_name,
        firmware_size,
        firmware_sha256,
    ):
        self.last_cache_check = (
            session_id,
            facility_id,
            ppu_id,
            firmware_name,
            firmware_size,
            firmware_sha256,
        )
        return {
            "ok": True,
            "firmware": {
                "cache_hit": False,
                "firmware_name": firmware_name,
                "firmware_size": firmware_size,
                "firmware_sha256": firmware_sha256,
            },
        }

    def cache_firmware(
        self,
        session_id,
        facility_id,
        ppu_id,
        firmware_name,
        firmware_sha256,
        firmware,
    ):
        self.last_cache_upload = (
            session_id,
            facility_id,
            ppu_id,
            firmware_name,
            firmware_sha256,
            firmware,
        )
        return {
            "ok": True,
            "firmware": {
                "cache_hit": True,
                "uploaded": True,
                "firmware_name": firmware_name,
                "firmware_size": len(firmware),
                "firmware_sha256": firmware_sha256,
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
        firmware_sha256=None,
    ):
        self.last_start = (
            facility_id,
            ppu_id,
            request,
            session_id,
            firmware_sha256,
        )
        return {
            "ok": True,
            "job": {
                "job_id": "programming-image-job-1",
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "queued",
            },
        }

    async def cancel_job(self, facility_id, ppu_id, job_id):
        return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}

    def read_output_file(self, facility_id, ppu_id, job_id, filename):
        return b""


class ProgrammingImageRestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_provider = PlasmaWebHandler.engineering_provider
        cls.provider = FakeProgrammingImageProvider()
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

    def test_catalog_and_session_publish_rest_v2_programming_image_names(self):
        status, payload = self.request("GET", "/api/engineering/targets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rest_contract_version"], WEB_REST_CONTRACT_VERSION)
        self.assertEqual(payload["programming_image_scope"], "connection-session-and-ppu")
        self.assertEqual(payload["firmware_scope"], "connection-session-and-ppu")

        status, payload = self.request("POST", "/api/engineering/session", {})
        self.assertEqual(status, 201)
        self.assertEqual(payload["rest_contract_version"], WEB_REST_CONTRACT_VERSION)
        self.assertEqual(
            payload["session"]["programming_image_cache_scope"],
            "connection-session-and-ppu",
        )
        self.assertEqual(
            payload["session"]["firmware_cache_scope"],
            "connection-session-and-ppu",
        )

    def test_canonical_programming_image_check_and_upload_routes(self):
        session_id = "1" * 32
        sha256 = "a" * 64
        status, payload = self.request(
            "POST",
            f"{self.target}/api/programming-images/check",
            {
                "session_id": session_id,
                "image_name": "image.bin",
                "image_size": 4096,
                "image_sha256": sha256,
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["programming_image"]["cache_hit"])
        self.assertEqual(payload["programming_image"]["image_name"], "image.bin")
        self.assertEqual(payload["programming_image"]["image_size"], 4096)
        self.assertEqual(payload["programming_image"]["image_sha256"], sha256)
        self.assertIn("firmware", payload)
        self.assertEqual(
            self.provider.last_cache_check,
            (session_id, "facility-01", "ppu-01", "image.bin", 4096, sha256),
        )

        status, payload = self.request(
            "POST",
            f"{self.target}/api/programming-images?session_id={session_id}&name=image.bin&sha256={sha256}",
            raw_body=b"image-bytes",
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 201)
        self.assertTrue(payload["programming_image"]["uploaded"])
        self.assertEqual(
            self.provider.last_cache_upload,
            (session_id, "facility-01", "ppu-01", "image.bin", sha256, b"image-bytes"),
        )

    def test_canonical_job_reference_routes_to_legacy_provider_boundary(self):
        session_id = "2" * 32
        sha256 = "b" * 64
        status, payload = self.request(
            "POST",
            f"{self.target}/api/jobs",
            {
                "site_id": 2,
                "operation": "program",
                "session_id": session_id,
                "image_name": "cached.bin",
                "image_sha256": sha256,
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["operation"], "program")
        _, _, request, routed_session, routed_sha = self.provider.last_start
        self.assertEqual(request.metadata["firmware_name"], "cached.bin")
        self.assertEqual(routed_session, session_id)
        self.assertEqual(routed_sha, sha256)

    def test_legacy_firmware_alias_remains_accepted(self):
        session_id = "3" * 32
        sha256 = "c" * 64
        status, payload = self.request(
            "POST",
            f"{self.target}/api/firmware/check",
            {
                "session_id": session_id,
                "firmware_name": "legacy.bin",
                "firmware_size": 64,
                "firmware_sha256": sha256,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["programming_image"]["image_name"], "legacy.bin")
        self.assertEqual(payload["firmware"]["firmware_name"], "legacy.bin")

    def test_conflicting_canonical_and_legacy_fields_are_rejected(self):
        status, payload = self.request(
            "POST",
            f"{self.target}/api/programming-images/check",
            {
                "session_id": "4" * 32,
                "image_name": "canonical.bin",
                "firmware_name": "legacy.bin",
                "image_size": 64,
                "firmware_size": 64,
                "image_sha256": "d" * 64,
                "firmware_sha256": "d" * 64,
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("disagree", payload["error"]["message"])

    def test_local_job_accepts_canonical_inline_image_fields(self):
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        encoded = base64.b64encode(b"inline-image").decode()
        request = handler._job_request(
            {
                "site_id": 1,
                "operation": "program",
                "image_name": "inline.bin",
                "image_base64": encoded,
            },
            client_id="test-client",
        )
        self.assertEqual(request.firmware, b"inline-image")
        self.assertEqual(request.metadata["firmware_name"], "inline.bin")


if __name__ == "__main__":
    unittest.main()
