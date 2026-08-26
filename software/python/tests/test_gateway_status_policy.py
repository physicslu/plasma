from __future__ import annotations

import asyncio
import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler, _gateway_settings_payload
from plasma_web.gateway_communication import ppu_response_budget_ms, request_with_gateway_policy
from plasma_web.gateway_settings import GatewayCommunicationPolicy


class FastPolicy:
    def __init__(self, *, timeout_s: float = 0.01, retry_count: int = 1) -> None:
        self.request_timeout_s = timeout_s
        self.ppu_request_timeout_ms = int(timeout_s * 1000)
        self.ppu_retry_count = retry_count
        self.revision = 1


class FastSettings:
    def __init__(self, policy: FastPolicy) -> None:
        self.policy = policy

    def snapshot(self):
        return self.policy


class TimeoutEngineeringProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.always_timeout = False

    async def status(self, facility_id, ppu_id, *, site_id=None, job_id=None):
        self.calls += 1
        if self.always_timeout or self.calls == 1:
            await asyncio.sleep(0.05)
        return {
            "ok": True,
            "ppu": {"facility_id": facility_id, "ppu_id": ppu_id, "site_count": 2},
            "sites": [
                {"site_id": 1, "enabled": True, "state": "idle"},
                {"site_id": 2, "enabled": True, "state": "idle"},
            ],
        }


class GatewayStatusPolicyTests(unittest.TestCase):
    def test_default_policy_exposes_complete_response_budget(self) -> None:
        self.assertEqual(ppu_response_budget_ms(GatewayCommunicationPolicy()), 47_000)
        payload = _gateway_settings_payload(
            {"revision": 1, "ppu_request_timeout_ms": 10_000, "ppu_retry_count": 3}
        )
        self.assertEqual(payload["gateway_settings"]["ppu_response_budget_ms"], 47_000)

    def test_derived_response_budget_tracks_current_gateway_policy(self) -> None:
        payload = _gateway_settings_payload(
            {"revision": 2, "ppu_request_timeout_ms": 15_000, "ppu_retry_count": 2}
        )
        self.assertEqual(payload["gateway_settings"]["ppu_response_budget_ms"], 48_000)

    def test_shared_policy_helper_retries_transient_failure(self) -> None:
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("first attempt")
            return "ok"

        result = asyncio.run(
            request_with_gateway_policy(
                operation,
                FastPolicy(timeout_s=0.02, retry_count=1),
                retry_backoff_s=0.001,
            )
        )
        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)


class GatewayStatusPolicyHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_provider = PlasmaWebHandler.engineering_provider
        cls.previous_settings = PlasmaWebHandler.gateway_settings
        cls.previous_backoff = PlasmaWebHandler.engineering_status_retry_backoff_s
        cls.provider = TimeoutEngineeringProvider()
        PlasmaWebHandler.engineering_provider = cls.provider
        PlasmaWebHandler.gateway_settings = FastSettings(FastPolicy(timeout_s=0.01, retry_count=1))
        PlasmaWebHandler.engineering_status_retry_backoff_s = 0.001
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaWebHandler.engineering_provider = cls.previous_provider
        PlasmaWebHandler.gateway_settings = cls.previous_settings
        PlasmaWebHandler.engineering_status_retry_backoff_s = cls.previous_backoff

    def request(self):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        conn.request(
            "GET",
            "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/status",
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    def test_gateway_times_out_first_provider_attempt_and_recovers_server_side(self) -> None:
        self.provider.calls = 0
        self.provider.always_timeout = False
        with redirect_stdout(io.StringIO()):
            status, payload = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["sites"]), 2)
        self.assertEqual(self.provider.calls, 2)

    def test_gateway_returns_service_unavailable_after_status_retry_exhaustion(self) -> None:
        self.provider.calls = 0
        self.provider.always_timeout = True
        try:
            with redirect_stdout(io.StringIO()):
                status, payload = self.request()
        finally:
            self.provider.always_timeout = False
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["error_code"], "E2002")
        self.assertEqual(payload["error"]["error_type"], "CONNECTION_TIMEOUT")
        self.assertEqual(self.provider.calls, 2)


if __name__ == "__main__":
    unittest.main()
