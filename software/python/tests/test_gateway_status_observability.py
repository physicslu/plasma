from __future__ import annotations

import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class DiagnosticEngineeringProvider:
    fail = False

    async def status(self, facility_id, ppu_id, *, site_id=None, job_id=None):
        if self.fail:
            raise RuntimeError("simulated provider failure")
        if job_id is not None:
            return {
                "ok": True,
                "job": {"job_id": job_id, "site_id": site_id or 1, "state": "success"},
            }
        return {
            "ok": True,
            "ppu": {"facility_id": facility_id, "ppu_id": ppu_id, "site_count": 2},
            "sites": [
                {"site_id": 1, "enabled": True, "state": "idle"},
                {"site_id": 2, "enabled": True, "state": "idle"},
            ],
        }


class GatewayStatusObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_provider = PlasmaWebHandler.engineering_provider
        cls.provider = DiagnosticEngineeringProvider()
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

    def request(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("GET", path)
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    @staticmethod
    def diagnostic_events(output: str):
        events = []
        for line in output.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("component") == "plasma-web-rest-gateway":
                events.append(payload)
        return events

    def test_ppu_level_status_logs_start_and_completion_latency(self):
        self.provider.fail = False
        capture = io.StringIO()
        with redirect_stdout(capture):
            status, payload = self.request(
                "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/status"
            )

        self.assertEqual(status, 200)
        self.assertEqual(len(payload["sites"]), 2)
        events = self.diagnostic_events(capture.getvalue())
        self.assertEqual(
            [event["event"] for event in events],
            ["engineering_ppu_status_start", "engineering_ppu_status_ok"],
        )
        completed = events[1]
        self.assertEqual(completed["facility_id"], "mock-facility-01")
        self.assertEqual(completed["ppu_id"], "mock-facility-01-ppu-01")
        self.assertEqual(completed["site_count"], 2)
        self.assertGreaterEqual(completed["elapsed_ms"], 0)

    def test_job_specific_status_does_not_emit_ppu_level_noise(self):
        self.provider.fail = False
        capture = io.StringIO()
        with redirect_stdout(capture):
            status, _ = self.request(
                "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/status?job=job-1&site=1"
            )

        self.assertEqual(status, 200)
        self.assertEqual(self.diagnostic_events(capture.getvalue()), [])

    def test_ppu_level_failure_logs_elapsed_error_and_request_boundary(self):
        self.provider.fail = True
        capture = io.StringIO()
        try:
            with redirect_stdout(capture):
                status, payload = self.request(
                    "/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/status"
                )
        finally:
            self.provider.fail = False

        self.assertEqual(status, 400)
        self.assertIn("simulated provider failure", payload["error"]["message"])
        events = self.diagnostic_events(capture.getvalue())
        self.assertEqual(
            [event["event"] for event in events],
            ["engineering_ppu_status_start", "engineering_ppu_status_error", "request_error"],
        )
        failed = events[1]
        self.assertEqual(failed["error_type"], "RuntimeError")
        self.assertGreaterEqual(failed["elapsed_ms"], 0)
        boundary = events[2]
        self.assertEqual(boundary["method"], "GET")
        self.assertEqual(
            boundary["path"],
            "/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/status",
        )


if __name__ == "__main__":
    unittest.main()
