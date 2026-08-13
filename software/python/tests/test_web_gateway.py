from __future__ import annotations

import base64
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class FakeClient:
    last_request = None
    async def status(self, **kwargs): return {"ok": True, "channels": [{"channel_id": 0}]}
    async def start(self, request):
        FakeClient.last_request = request
        return {"ok": True, "job": {"job_id": "web-job-1", "state": "queued"}}
    async def cancel(self, job_id): return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}


class WebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PlasmaWebHandler.client_factory = staticmethod(FakeClient)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, raw, {"Content-Type": "application/json"} if raw else {})
        response = conn.getresponse(); payload = json.loads(response.read()); conn.close()
        return response.status, payload

    def test_status(self):
        status, payload = self.request("GET", "/api/status")
        self.assertEqual(status, 200); self.assertTrue(payload["ok"])

    def test_start_program_upload(self):
        firmware = b"\x01\x02\x03"
        status, payload = self.request("POST", "/api/jobs", {"channel_id": 1, "operation": "program", "firmware_name": "fw.bin", "firmware_base64": base64.b64encode(firmware).decode()})
        self.assertEqual(status, 202); self.assertEqual(payload["job"]["job_id"], "web-job-1")
        self.assertEqual(FakeClient.last_request.firmware, firmware)

    def test_verify_requires_firmware(self):
        status, payload = self.request("POST", "/api/jobs", {"channel_id": 0, "operation": "verify"})
        self.assertEqual(status, 400); self.assertFalse(payload["ok"])

    def test_cancel(self):
        status, payload = self.request("POST", "/api/jobs/web-job-1/cancel", {})
        self.assertEqual(status, 200); self.assertTrue(payload["job"]["cancel_requested"])


if __name__ == "__main__": unittest.main()
