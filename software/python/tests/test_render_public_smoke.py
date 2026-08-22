from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


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
        if self.path == "/api/health/ready":
            type(self).readiness_calls += 1
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

    def test_unpinned_smoke_can_accept_ready_service_without_deployment_metadata(self) -> None:
        payload = self.wait(None)

        self.assertTrue(payload["ok"])
        self.assertEqual(FakeRenderHandler.readiness_calls, 1)

    def test_pinned_smoke_fails_closed_when_deployment_metadata_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "deployment identity is not available"):
            self.wait("a" * 40)

        self.assertEqual(FakeRenderHandler.readiness_calls, 0)

    def test_pinned_smoke_fails_closed_while_wrong_commit_is_serving(self) -> None:
        FakeRenderHandler.deployed_commit = "b" * 40

        with self.assertRaisesRegex(RuntimeError, "waiting for expected"):
            self.wait("a" * 40)

        self.assertEqual(FakeRenderHandler.readiness_calls, 0)

    def test_pinned_smoke_accepts_readiness_only_after_exact_commit_match(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
