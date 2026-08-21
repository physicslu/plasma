from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.batch_runtime import BatchRuntimeManager
from plasma_web.gateway import PlasmaWebHandler
from tests.test_batch_runtime import FakeBatchProvider


class BatchWebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_runtime = PlasmaWebHandler.batch_runtime
        cls.provider = FakeBatchProvider()
        cls.runtime = BatchRuntimeManager(cls.provider, poll_interval_s=0.001)
        PlasmaWebHandler.batch_runtime = cls.runtime
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.runtime.close()
        PlasmaWebHandler.batch_runtime = cls.previous_runtime

    def request(self, method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def wait_terminal(self, batch_id: str, timeout_s: float = 2.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status, payload = self.request("GET", f"/api/batches/{batch_id}")
            self.assertEqual(status, 200)
            if payload["batch"]["state"] in {"success", "partial", "error", "cancelled"}:
                return payload["batch"]
            time.sleep(0.01)
        self.fail(f"Batch {batch_id} did not finish")

    def test_create_and_get_batch_roundtrip(self):
        status, payload = self.request(
            "POST",
            "/api/batches",
            {
                "targets": [
                    {"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [1, 2]},
                ],
                "operations": ["read", "erase"],
                "execution_policy": {
                    "repeat_count": 3,
                    "site_retry_limit": 2,
                    "failed_site_stop_threshold": 2,
                },
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["rest_contract_version"], "3")
        self.assertEqual(payload["batch"]["operations"], ["erase", "read"])
        batch_id = payload["batch"]["batch_id"]
        final = self.wait_terminal(batch_id)
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["execution_policy"]["repeat_count"], 3)
        self.assertEqual(final["execution_policy"]["site_retry_limit"], 2)
        self.assertEqual(final["site_counts"]["success"], 2)

    def test_program_batch_accepts_one_asset_snapshot(self):
        image = b"batch-rest-image" * 16
        digest = hashlib.sha256(image).hexdigest()
        status, payload = self.request(
            "POST",
            "/api/batches",
            {
                "session_id": "1" * 32,
                "targets": [
                    {"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [1, 2]},
                ],
                "operations": ["program", "verify"],
                "execution_policy": {
                    "repeat_count": 2,
                    "site_retry_limit": 1,
                    "failed_site_stop_threshold": None,
                },
                "asset": {
                    "asset_name": "batch.bin",
                    "asset_type": "image",
                    "asset_format": "binary",
                    "asset_size": len(image),
                    "asset_sha256": digest,
                    "asset_base64": base64.b64encode(image).decode(),
                },
            },
        )
        self.assertEqual(status, 202)
        batch_id = payload["batch"]["batch_id"]
        final = self.wait_terminal(batch_id)
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["asset"]["sha256"], digest)
        self.assertEqual(final["asset"]["size_bytes"], len(image))
        self.assertEqual(final["operation_statistics"]["program"]["logical_executions"], 4)
        self.assertEqual(final["operation_statistics"]["verify"]["logical_executions"], 4)
        cached = [entry for entry in self.provider.cache_log if entry[2] == digest]
        self.assertEqual(len(cached), 1)

    def test_threshold_cannot_exceed_selected_sites(self):
        status, payload = self.request(
            "POST",
            "/api/batches",
            {
                "targets": [
                    {"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [1, 2]},
                ],
                "operations": ["erase"],
                "execution_policy": {
                    "repeat_count": 1,
                    "site_retry_limit": 0,
                    "failed_site_stop_threshold": 3,
                },
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_unknown_batch_is_structured_error(self):
        status, payload = self.request("GET", "/api/batches/batch-does-not-exist")
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
