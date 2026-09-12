from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from plasma_manager.client import PPUHttpClient, PPUTransportError


class _HeaderCaptureHandler(BaseHTTPRequestHandler):
    observed: list[dict[str, str]] = []

    def log_message(self, format: str, *args: object) -> None:
        return

    def _respond(self) -> None:
        type(self).observed.append({key.lower(): value for key, value in self.headers.items()})
        body = json.dumps({"ok": True, "gateway": "alive"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._respond()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self._respond()


@pytest.fixture
def ppu_server():
    _HeaderCaptureHandler.observed = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HeaderCaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _endpoint(server: ThreadingHTTPServer) -> str:
    return f"http://127.0.0.1:{server.server_port}"


def _set_access_identity(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_ORIGIN", origin)
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_CLIENT_ID", "service-id.example.access")
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET", "service-secret")


def test_service_identity_is_sent_only_to_exact_configured_origin(monkeypatch: pytest.MonkeyPatch, ppu_server):
    endpoint = _endpoint(ppu_server)
    _set_access_identity(monkeypatch, endpoint)

    client = PPUHttpClient(endpoint, timeout_s=1.0)
    client.liveness()

    observed = _HeaderCaptureHandler.observed[-1]
    assert observed["cf-access-client-id"] == "service-id.example.access"
    assert observed["cf-access-client-secret"] == "service-secret"


def test_service_identity_is_not_leaked_to_other_origin(monkeypatch: pytest.MonkeyPatch, ppu_server):
    endpoint = _endpoint(ppu_server)
    _set_access_identity(monkeypatch, "https://ppu-managed.example.invalid")

    client = PPUHttpClient(endpoint, timeout_s=1.0)
    client.liveness()

    observed = _HeaderCaptureHandler.observed[-1]
    assert "cf-access-client-id" not in observed
    assert "cf-access-client-secret" not in observed


def test_incomplete_service_identity_fails_closed(monkeypatch: pytest.MonkeyPatch, ppu_server):
    endpoint = _endpoint(ppu_server)
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_ORIGIN", endpoint)
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_CLIENT_ID", "service-id.example.access")
    monkeypatch.delenv("PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET", raising=False)

    with pytest.raises(PPUTransportError, match="service identity is incomplete"):
        PPUHttpClient(endpoint, timeout_s=1.0)


def test_browser_relay_headers_cannot_override_service_identity(monkeypatch: pytest.MonkeyPatch, ppu_server):
    endpoint = _endpoint(ppu_server)
    _set_access_identity(monkeypatch, endpoint)

    client = PPUHttpClient(endpoint, timeout_s=1.0)
    status, _, _ = client.relay(
        "POST",
        "/api/jobs",
        headers={
            "Content-Type": "application/json",
            "CF-Access-Client-Id": "attacker-value",
            "CF-Access-Client-Secret": "attacker-secret",
        },
        body=b"{}",
        timeout_s=1.0,
        max_response_bytes=1024,
    )

    assert status == 200
    observed = _HeaderCaptureHandler.observed[-1]
    assert observed["cf-access-client-id"] == "service-id.example.access"
    assert observed["cf-access-client-secret"] == "service-secret"
