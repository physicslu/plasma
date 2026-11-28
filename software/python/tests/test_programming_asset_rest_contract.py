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

    def test_catalog_publishes_rest_v3_asset_contract(self):
        status, payload = self.request("GET", "/api/engineering/targets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rest_contract_version"], WEB_REST_CONTRACT_VERSION)
        self.assertEqual(WEB_REST_CONTRACT_VERSION, "3")
        self.assertEqual(payload["programming_asset_scope"], "connection-session-and-ppu")
        self.assertIn("serial_number", payload["supported_asset_types"])

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
                "asset_size": len(data),
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
                    "asset_size": len(data),
                    "asset_sha256": sha256,
                    "asset_base64": encoded,
                },
                client_id="test-client",
            )

    def test_unknown_or_session_asset_fields_fail_closed(self):
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        for extra in ({"unexpected": True}, {"session_id": "1" * 32}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                handler._job_request({"site_id": 1, "operation": "erase", **extra},
                                     client_id="test-client")

    def test_retired_rest_routes_are_not_available(self):
        # The session Programming Asset cache existed only for the retired
        # Engineering Job path (U7).
        for path in (
            f"{self.target}/api/programming-images/check",
            f"{self.target}/api/firmware/check",
            f"{self.target}/api/programming-assets/check",
            f"{self.target}/api/programming-assets",
            "/api/engineering/session",
        ):
            with self.subTest(path=path):
                status, _payload = self.request("POST", path, {})
                self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
