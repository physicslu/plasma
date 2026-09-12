from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/tests/test-render-public-smoke.py"
SPEC = importlib.util.spec_from_file_location("plasma_render_public_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)


class FakeRenderHandler(BaseHTTPRequestHandler):
    deployed_commit: str | None = None
    readiness_calls = 0
    last_readiness_path: str | None = None

    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/deployment.json":
            if self.deployed_commit is None:
                self._send(HTTPStatus.OK, "text/html", b"<html>old deployment</html>")
                return
            body = json.dumps({"git_commit": self.deployed_commit}).encode()
            self._send(HTTPStatus.OK, "application/json", body)
            return
        if self.path in {"/api/health/ready", "/api/manager/ppu/api/health/ready"}:
            type(self).readiness_calls += 1
            type(self).last_readiness_path = self.path
            body = json.dumps(
                {
                    "ok": True,
                    "service": "plasma-web-rest-gateway",
                    "gateway": "alive",
                    "execution": "ready",
                    "ppu_id": "render-demo-ppu",
                }
            ).encode()
            self._send(HTTPStatus.OK, "application/json", body)
            return
        if self.path == "/":
            self._send(HTTPStatus.OK, "text/html", b"<html>Plasma PPU Console</html>")
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found")


class RenderPublicSmokePinningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRenderHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self) -> None:
        FakeRenderHandler.deployed_commit = None
        FakeRenderHandler.readiness_calls = 0
        FakeRenderHandler.last_readiness_path = None

    def report(self, expected_commit: str | None) -> object:
        return SMOKE.SmokeReport(origin=self.origin, expected_commit=expected_commit)

    def wait(self, expected_commit: str | None):
        return SMOKE.wait_until_ready(
            self.origin,
            expected_commit=expected_commit,
            wake_timeout=0.12,
            poll_interval=0.02,
            request_timeout=0.1,
            report=self.report(expected_commit),
        )

    def test_unpinned_smoke_observes_legacy_deployment_readiness(self) -> None:
        payload = self.wait(None)

        self.assertTrue(payload["ok"])
        self.assertEqual(FakeRenderHandler.readiness_calls, 1)
        self.assertEqual(FakeRenderHandler.last_readiness_path, "/api/health/ready")

    def test_pinned_smoke_fails_closed_when_deployment_metadata_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "deployment identity is not available"):
            self.wait("a" * 40)

        self.assertEqual(FakeRenderHandler.readiness_calls, 0)

    def test_pinned_smoke_fails_closed_while_wrong_commit_is_serving(self) -> None:
        FakeRenderHandler.deployed_commit = "b" * 40

        with self.assertRaisesRegex(RuntimeError, "waiting for expected"):
            self.wait("a" * 40)

        self.assertEqual(FakeRenderHandler.readiness_calls, 0)

    def test_pinned_smoke_uses_managed_readiness_after_exact_commit_match(self) -> None:
        expected = "c" * 40
        FakeRenderHandler.deployed_commit = expected
        report = self.report(expected)

        payload = SMOKE.wait_until_ready(
            self.origin,
            expected_commit=expected,
            wake_timeout=0.12,
            poll_interval=0.02,
            request_timeout=0.1,
            report=report,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(report.observed_commit, expected)
        self.assertEqual(FakeRenderHandler.readiness_calls, 1)
        self.assertEqual(FakeRenderHandler.last_readiness_path, "/api/manager/ppu/api/health/ready")
        self.assertEqual(report.checks["routing"], "MANAGED")

    @staticmethod
    def contract_payload(path: str) -> dict[str, object]:
        normalized = path.removeprefix("/api/manager/ppu")
        if normalized.startswith("/api/status?job="):
            return {"job": {"job_id": normalized.split("=", 1)[1], "state": "success"}}
        if normalized == "/api/status":
            return {"ppu": {"ppu_id": "render-demo-ppu"}, "sites": [{} for _ in range(8)]}
        if normalized == "/api/engineering/targets":
            return {
                "ok": True,
                "rest_contract_version": "3",
                "provider": "mock",
                "facility_count": 8,
                "ppu_count": 32,
                "site_count": 160,
            }
        if normalized == "/api/mock/runtime":
            return {
                "ok": True,
                "rest_contract_version": "3",
                "mock_runtime": {
                    "operations": {name: {} for name in ("erase", "program", "verify", "read")},
                    "default_image_size_bytes": 1024,
                },
            }
        if normalized == "/api/devices/search?q=stm32&limit=1":
            return {
                "ok": True,
                "rest_contract_version": "3",
                "catalog_size": 912,
                "results": [{"identifier": "STM32F103C8T6"}],
            }
        raise AssertionError(f"unexpected contract path: {path}")

    def test_unpinned_pr_observation_skips_new_device_catalog_and_program_contracts(self) -> None:
        calls: list[str] = []

        def request_json(_origin: str, path: str, *, timeout: float):
            calls.append(path)
            return self.contract_payload(path)

        report = self.report(None)
        with patch.object(SMOKE, "request_json", side_effect=request_json):
            SMOKE.assert_contracts(self.origin, timeout=0.1, report=report)

        self.assertEqual(report.checks["api:device-catalog-search"], "SKIP_UNPINNED")
        self.assertNotIn("/api/devices/search?q=stm32&limit=1", calls)
        self.assertNotIn("api:managed-mock-program", report.checks)

    def test_unpinned_pr_observation_accepts_the_current_main_topology(self) -> None:
        def request_json(_origin: str, path: str, *, timeout: float):
            payload = self.contract_payload(path)
            if path == "/api/engineering/targets":
                return {**payload, "facility_count": 3, "ppu_count": 12, "site_count": 60}
            return payload

        report = self.report(None)
        with patch.object(SMOKE, "request_json", side_effect=request_json):
            SMOKE.assert_contracts(self.origin, timeout=0.1, report=report)

        self.assertEqual(report.checks["api:engineering-targets"], "PASS")

    def test_pinned_post_deployment_smoke_enforces_managed_contract_and_programs(self) -> None:
        calls: list[str] = []
        posts: list[str] = []

        def request_json(_origin: str, path: str, *, timeout: float):
            calls.append(path)
            return self.contract_payload(path)

        def request_json_post(_origin: str, path: str, payload: dict, *, timeout: float):
            posts.append(path)
            self.assertEqual(payload["site_id"], 1)
            return {"job": {"job_id": "job-1", "state": "queued"}}

        report = self.report("d" * 40)
        with (
            patch.object(SMOKE, "request_json", side_effect=request_json),
            patch.object(SMOKE, "request_json_post", side_effect=request_json_post),
        ):
            SMOKE.assert_contracts(self.origin, timeout=0.1, report=report)

        self.assertEqual(report.checks["api:device-catalog-search"], "PASS")
        self.assertEqual(report.checks["api:managed-mock-program"], "PASS")
        self.assertIn("/api/manager/ppu/api/devices/search?q=stm32&limit=1", calls)
        self.assertIn("/api/manager/ppu/api/status?job=job-1", calls)
        self.assertEqual(posts, ["/api/manager/ppu/api/jobs"])


if __name__ == "__main__":
    unittest.main()
