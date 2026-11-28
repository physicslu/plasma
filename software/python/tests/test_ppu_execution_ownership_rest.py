from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.gateway import PlasmaWebHandler


class OwnershipClient:
    """Stand-in PPU client behind the Gateway's direct /api/jobs route."""

    last_request = None
    reject = False

    async def start(self, request):
        OwnershipClient.last_request = request
        if OwnershipClient.reject:
            raise PlasmaError(
                ErrorCode.PPU_BUSY,
                "PPU is owned by another active execution",
                recoverable=True,
                context={
                    "active_owner_kind": "batch",
                    "active_owner_id": "batch-a",
                    "requested_owner_kind": request.metadata.get("execution_owner_kind"),
                    "requested_owner_id": request.metadata.get("execution_owner_id"),
                },
            )
        return {
            "ok": True,
            "job": {
                "job_id": request.job_id,
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "queued",
            },
        }


class PPUExecutionOwnershipRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_factory = PlasmaWebHandler.client_factory
        PlasmaWebHandler.client_factory = staticmethod(OwnershipClient)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaWebHandler.client_factory = cls.previous_factory

    def setUp(self):
        OwnershipClient.last_request = None
        OwnershipClient.reject = False

    def post_job(self, body, path="/api/jobs"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    def test_explicit_rest_owner_is_preserved_as_execution_metadata(self):
        status, payload = self.post_job(
            {
                "site_id": 1,
                "operation": "erase",
                "execution_owner_id": "client-a",
            }
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["job"]["site_id"], 1)
        request = OwnershipClient.last_request
        self.assertIsNotNone(request)
        self.assertEqual(request.metadata["execution_owner_kind"], "rest_client")
        self.assertEqual(request.metadata["execution_owner_id"], "client-a")

    def test_ppu_busy_is_http_409_with_structured_conflict_context(self):
        OwnershipClient.reject = True
        status, payload = self.post_job(
            {
                "site_id": 1,
                "operation": "erase",
                "execution_owner_id": "client-b",
            }
        )
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])
        error = payload["error"]
        self.assertEqual(error["error_code"], ErrorCode.PPU_BUSY.value)
        self.assertEqual(error["error_type"], "PPU_BUSY")
        self.assertTrue(error["recoverable"])
        self.assertEqual(error["context"]["active_owner_id"], "batch-a")
        self.assertEqual(error["context"]["requested_owner_id"], "client-b")

    def test_invalid_explicit_rest_owner_fails_before_provider_submission(self):
        status, payload = self.post_job(
            {
                "site_id": 1,
                "operation": "erase",
                "execution_owner_id": "",
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("execution_owner_id", payload["error"]["message"])
        self.assertIsNone(OwnershipClient.last_request)


if __name__ == "__main__":
    unittest.main()
